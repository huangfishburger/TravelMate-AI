# Trip memory

`main.py` keeps one in-process `memory` object alongside the conversation `history`. Each new user turn goes through `intent.py`, which returns explicit `state_changes` and whether the user started a different trip. The changes update `trip_state` before planning; later user corrections replace earlier values. The planner and itinerary evaluator both receive the current state and the older conversation summary.

`trip_state` holds origin, destination, traveler count, dates, hard constraints (including budget currency), soft preferences, selected flight/hotel, and user-controlled lock flags. When a total budget has no explicit currency, the agent defaults to the departure location's currency when that location is known (for example, TPE → TWD); an explicit currency takes precedence. A selected option means it was chosen in the plan; it does not mean it was booked. Planner extraction cannot replace a locked option. Users can explicitly change or unlock it.

Flight and hotel search tools accept a `currency` argument. For a trip with a budget, the agent forces both search tools and `check_budget` to use the budget currency; price filters use that unit too. Searches without a known currency default to USD. `check_budget` still performs arithmetic only, so other estimated costs must be expressed in the same currency before checking.
When the traveler count is known, the planner sends it as the adult count to flight and hotel searches. The flight quote is for that searched group and should be entered once in `check_budget`; adult-fare searches are only an approximation when the party includes children or infants.

The five most recent user turns and their responses remain in `history`. Once a sixth turn arrives, older dialogue is summarized, and its detailed messages are removed from the context. Image bytes and tool outputs are excluded from the summary. This is session memory only: exiting the CLI loses it. `/memory` displays the current state and summary; `/reset` clears both history and memory.

For Python callers, reuse both containers across turns:

```python
from agent import run_agent
from memory import new_memory

history = []
memory = new_memory()
run_agent("Plan a Seattle trip", history=history, memory=memory)
run_agent("Actually, make the pace relaxed", history=history, memory=memory)
```

`max_rounds=8` still limits model/tool rounds within one planning attempt. It does not limit the number of user turns.

The CLI prints token totals after each turn, including counts by model-call phase. Test JSONL rows contain `token_usage`, and the test summary aggregates it across cases. The test-only reviewer has its own `reviewer` phase. `missing_usage_calls` counts API responses without usage data; these are not estimated. Existing result files only gain the new per-case field when rerun.
