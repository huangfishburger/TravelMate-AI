# Travelmate

A conversational travel planner built in Python. Users can plan trips through a local web interface or CLI, upload images, and revise their requirements. The agent searches for flights, hotels, and places; checks trip budgets; and evaluates itinerary quality before responding. **It does not book flights or hotels.**

## Architecture

```mermaid
flowchart TD
    U[User request<br/>web or CLI] --> I[Understand intent and constraints]
    I --> M[Update trip state and conversation memory]
    M --> P[Plan the trip]
    P --> S[Search real flights, hotels, and places<br/>when needed]
    S --> V[Validate costs against the budget<br/>when one is supplied]
    V --> E[Evaluate itinerary quality<br/>when a full plan is produced]
    V -->|Over budget: retry up to 2 times| P
    E -->|Score below 7: retry up to 2 times| P
    E --> F[Final answer]
```

The diagram shows a full itinerary request. `intent.py` identifies the request and explicit changes to trip requirements; `memory.py` preserves trip state and summarizes older turns. If supplied requirements materially conflict, the agent asks for clarification before planning. `agent.py` runs the planner and any replans, `tools/` supplies search results and budget calculations, and `evaluator.py` scores itinerary quality. Narrow questions can skip searches, budget checks, or evaluation when they do not apply. After the retry limit, the agent explains an unresolved budget shortfall or returns the latest quality revision.

Shared helpers live in `utils/`: `utils/currency.py` for currency defaults, `utils/multimodal.py` for image input, `utils/token_usage.py` for token accounting, plus budget, error, and tool-output helpers. The 50-case test runner and independent reviewer live in `tests/`; they assess the project and are not part of the user-facing request flow.

## Setup and run

The following commands use Windows PowerShell. From the project root:

```powershell
py -3 -m venv venv
.\venv\Scripts\python.exe -m pip install openai python-dotenv serpapi
```

Create a `.env` file with your own credentials:

```dotenv
OPENAI_API_KEY=your_openai_api_key
SERPAPI_API_KEY=your_serpapi_api_key
```

`.env` is listed in `.gitignore`. Keep credentials out of source files and commits.

Start the web interface:

```powershell
.\venv\Scripts\python.exe web_app.py
```

Open <http://127.0.0.1:8000>. The server listens on localhost only. The interface accepts text and up to three PNG, JPEG, WEBP, or GIF images (8 MB each) through the **+** button. It displays trip state, chat and itinerary, selected flight and hotel details, a cost breakdown, and Agent Activity. The activity panel shows observable searches and replanning events rather than private model reasoning. **New trip** clears that browser session's conversation and memory.

During planning, the chat and Agent Activity panel show the current task and completed tool actions as they happen, including searches, budget checks, evaluation, and replanning.

Once you like an itinerary, choose **Edit & export** on its response. A separate page lets you revise a Markdown copy with a live preview and download it as `.md`. The draft stays in the current browser tab; it does not alter the agent's original plan or budget check.

Start the CLI instead with:

```powershell
.\venv\Scripts\python.exe main.py
```

CLI commands: `/image` attaches an image, `/memory` displays trip memory, `/reset` clears conversation and memory, and `/exit` quits.

## Planning, budgets, and memory

- `trip_state` tracks origin, destination, traveler count, dates, hard constraints, soft preferences, selected flights and hotels, and user-locked selections. Explicit user updates replace earlier values.
- When the traveler count is known, flight and hotel searches pass it as the adult count; flight fares returned for that group are used once in the budget rather than multiplied again. If child or infant fares are needed, adult pricing is only an approximation.
- The five most recent user turns remain in short-term history; older dialogue is summarized. Web and CLI memory is in-process only and is lost when the application restarts.
- A trip with a total budget uses `check_budget`. An over-budget plan triggers up to two budget replans. An itinerary with an evaluator average below 7 triggers up to two quality replans. `max_rounds=8` limits model/tool rounds **within one planning attempt**; it does not limit the number of user conversations.
- When a budget has no explicit currency, the agent defaults to the departure location's currency when recognized (for example, TPE to TWD). Explicit currency takes precedence. The mapping in `utils/currency.py` covers selected departure locations, so unfamiliar origins still depend on intent classification. Flight and hotel searches use the resulting budget currency. `check_budget` only adds numbers: it does not convert currencies.
- Hotel searches use check-in and check-out dates. For multi-night stays, the planner should use the full-stay price rather than treating a nightly rate as the total.
- If dates are undecided, the agent can offer a flexible plan, but it must not invent date-specific flights, prices, or availability. Listed options are not reservations.

## Tests

Run unit tests without calling external APIs:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
```

List selected cases from the 50-case suite without executing them:

```powershell
.\venv\Scripts\python.exe tests/run_cases.py --ids 1 6 21
```

Execute selected cases with real OpenAI and search API calls, saving results to a separate file:

```powershell
.\venv\Scripts\python.exe tests/run_cases.py --ids 1 6 21 --execute --output tests/results/smoke.jsonl
```

Each JSONL record includes tool traces, deterministic rule checks, production evaluator scores, independent reviewer results, and token usage. `tests/results/smoke.summary.json` aggregates case statuses and tokens. By default, a run overwrites the selected output file; use `--resume` to keep it and skip valid completed results. See [test-case expectations](tests/EXPECTED_BEHAVIOR.md) for the review rules.

Additional details: [web interface](WEB.md), [multimodal input](MULTIMODAL.md), and [memory](MEMORY.md).
