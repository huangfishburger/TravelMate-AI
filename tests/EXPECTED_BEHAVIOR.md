# Test-case expectations

`test_case.json` retains the original 50 prompts and adds `expected` to each case.
These are test specifications; a runner still needs to implement the checks.

- `allowed_response_types`: acceptable outcomes, conditional on available data.
  A search failure explanation is valid only when searches actually fail. A budget
  shortfall explanation needs checked costs and the bounded retry behavior.
- `hard_constraints`: user requirements. `requested_days` records the user's
  wording; conflicting inclusive date ranges are handled by `clarification_behavior`.
  Preserve fixed dates and explain arrival/departure days or ask for clarification.
  Airport selection for city codes such as NYC must serve the requested destination.
- `soft_preferences`: priorities rather than mandatory filters. A justified
  compromise can pass, especially when needed to preserve a hard constraint.
- `clarification_behavior`: missing-input and ambiguity rules. Do not invent dates
  for live searches. An undated itinerary can pass when it explains assumptions.
- `tool_behavior`: tools are required when relevant inputs are available and the
  requested components need searching, not unconditionally on every response.
  A clarification turn does not need a budget check. Hotel nightly caps are not
  total trip budgets. Search failure and unavailable options must not be fabricated.
- `budget_behavior`: check a final budgeted itinerary, retry if over budget, then
  explain the shortfall if limits are reached. The retry limit applies per planner
  run; quality replanning can start another planner run. Missing traveler counts
  require explicit assumptions or clarification. Prices must cover the same scope.
- `quality_behavior`: four-score evaluation applies only to proposed itineraries.
  Scores below 7 trigger up to two revisions. A remaining low score is a quality
  finding, not automatically a control-flow failure. Clarifications and explanations
  without an itinerary do not trigger quality replanning.
- `output_behavior`: section ordering applies only when a full itinerary is returned.
  Simple queries must remain focused and must not acquire an invented total budget.

No case presumes that cheap travel is necessarily feasible or that a preferred
option is available. Verify these outcomes against recorded tool results, not the
category name. Separate deterministic checks, model-reviewed quality, and manual
review in the eventual report. Overall score cannot override a hard-constraint
violation.

## Batch runner

The production planner now classifies request intent and the user-supplied total
budget (including conversation context) once per new user turn. Quality replanning
reuses the same intent result.
Intent also emits needs_clarification, ambiguities, and clarification_question.
If clarification is required, the agent returns the question immediately without
planner, searches, or evaluator calls. The question and user message are committed
to history so a subsequent reply can resolve the ambiguity. This is a model-based
decision; tests must still verify whether ambiguity detection is correct.
For this intent clarification path, final_itinerary_budget_check is
not_applicable, not unknown. The reviewer still checks whether the clarification
itself is appropriate; no full-itinerary success is implied.

For budgeted
itineraries or explicit budget checks, unchecked responses use a typed envelope:
itinerary/budget_answer/clarification/failure_explanation. An itinerary or budget
answer without a successful tool calculation is blocked, and the next request
forces check_budget. Clarifications and failure explanations may return without
a check. A conflicting total_budget argument is rejected. The guard still depends
on model intent/response-type classification, so semantic review should check
misclassification. Intent and missing-check events are saved in the trace.

List selected cases without making API calls:

```powershell
.\venv\Scripts\python.exe tests/run_cases.py --ids 1 6 21 46
```

Execute selected cases with real model and search APIs, saving one JSON record
per case immediately:

```powershell
.\venv\Scripts\python.exe tests/run_cases.py --ids 1 6 21 46 --execute
.\venv\Scripts\python.exe tests/run_cases.py --execute --resume
```

Use `--category basic` to select a category, `--output tests/results/baseline.jsonl`
to separate runs, and `--quality-replans 0` for the baseline without quality retries.
Resume skips completed cases only when case content, settings, and relevant source
fingerprints match. Errors are retried. The runner overwrites an existing
output by default. Use `--resume` to retain existing results and continue, or use
a new output to retain independent repeated trials.

Each record includes answer, expected, trace, evaluation history, retry counts,
elapsed time, and deterministic checks. Model-call trace events include token usage
when supplied by the API. A summary is written beside the JSONL output. Exceptions
are recorded and execution continues with the next case; a partial trace is retained.

Semantic checks run through the test-only LLM reviewer in `tests/reviewer.py` by
default. It receives prompt, expected, final answer, tool evidence, and unresolved
rule checks. Production evaluator scores and previous drafts are excluded to avoid
anchoring.
Tool results sent to the reviewer retain all options with selected evidence fields
(flight legs, airports, times, airlines, prices, layovers; hotel names, star classes,
guest ratings, rates, coordinates and amenities; place locations, hours and types).
Images, booking URLs, search metadata and tokens are omitted. Original tool results
remain in the saved trace. Missing summary fields must not be interpreted as absence.

It judges selected-option compliance, preferences, response scope,
assumptions, layout, timing, geographic efficiency, and coherence independently.
Every expected hard key, soft preference, and unknown rule must be covered once;
missing coverage is a reviewer error. Reports are saved under `semantic_review`.

Hard findings separate `status` (met/unmet/unknown/not_applicable) from `handling`
(appropriate/inappropriate/unknown). An honest, supported explanation of an unmet
constraint can be correct handling without claiming that the constraint was met.
Soft findings use met/justified_tradeoff/ignored/unknown/not_applicable. Evidence
must identify answer passages or trace event indexes; filters alone do not establish
selected-option compliance. Deterministic failures cannot be overridden by review.
Unknown evidence yields `needs_review`; inappropriate handling or ignored preferences
yield `fail`. LLM passes remain model judgments and should be manually sampled.
The reviewer now also returns four mandatory `completeness` findings: selected
flight (including return), trip cost scope, hotel full-stay total, and daily
feasibility. Any unknown required finding prevents `pass`; a demonstrated error
causes `fail`. Non-applicable components are explicitly labeled.
Applicability is determined from the test case and final response: an undated
local itinerary without a total budget does not require a selected flight, exact
trip-wide costs, or a hotel booking total. For routes with a requested return date,
a reviewer `pass` on flight selection is downgraded to `unknown` unless a timed
return leg appears in search evidence. Daily feasibility remains reviewable for
all complete itineraries. The prompt and `expected` have always been supplied to
the reviewer; this rule fixes the scope of its judgment.
`quality_target_met` reports the production evaluator result separately.

Use `--no-reviewer` for deterministic checks plus pending manual semantic review,
or `--reviewer-model MODEL` to configure the test reviewer independently. Reviewer
calls are additional API calls. Reviewer errors preserve the final answer and trace,
report `needs_review` unless a rule already failed, and are eligible for resume.
Resume currently reruns the entire case when a reviewer error occurred.

This runner currently uses live searches when executing. Fixed search fixtures are
not implemented yet. Trace files contain
prompts and tool results; keep them local unless intentionally shared.
