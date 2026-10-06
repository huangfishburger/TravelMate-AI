# Travelmate

A conversational travel planner built in Python. Users can plan trips through a local web interface or CLI, upload images, and revise their requirements. The agent searches for flights, hotels, and places; checks trip budgets; and evaluates itinerary quality before responding. **It does not book flights or hotels.**

## Architecture

```mermaid
flowchart LR
    U[User] --> W[Web UI<br/>web/ + web_app.py]
    U --> C[CLI<br/>main.py]
    W --> A[run_agent<br/>agent.py]
    C --> A

    A --> I[Intent and ambiguity detection<br/>intent.py]
    I --> M[Trip state and five recent turns<br/>memory.py]
    M --> S[Summary of older turns]
    A --> U[Shared helpers<br/>utils/]
    A --> P[Planner<br/>OpenAI Responses API]
    P --> T[Tool registry and execution<br/>tools/registry.py]
    T --> F[Flight, hotel, and place search<br/>SerpApi]
    T --> B[Budget calculation<br/>check_budget]
    B -->|Over budget: up to two replans| P
    P --> E[Itinerary quality scoring<br/>evaluator.py]
    E -->|Below 7: up to two replans| P
    E --> A
    A --> W
    A --> C

    R[50-case batch runner<br/>tests/run_cases.py] --> A
    R --> V[Independent test reviewer<br/>tests/reviewer.py]
```

For each user turn, `intent.py` identifies the request and explicit changes to trip requirements. It asks for clarification only when supplied requirements materially conflict. `agent.py` manages tool calls, budget replanning, and quality replanning. The production `evaluator.py` scores itinerary realism, geographic efficiency, preference alignment, and overall quality. `tools/` contains external searches and the budget check. Shared helpers now live in `utils/`: `utils/currency.py` for currency defaults, `utils/multimodal.py` for image input, `utils/token_usage.py` for token accounting, plus budget, error, and tool-output helpers. `tests/reviewer.py` is an **independent, test-only reviewer**; it does not participate in user-facing planning.

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
