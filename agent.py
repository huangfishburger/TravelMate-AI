import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from instructions import INSTRUCTIONS, BUDGET_REPLAN_INSTRUCTIONS, BUDGET_EXHAUSTED_INSTRUCTIONS
from tools.registry import TOOLS, execute_tool
from utils.errors import error_details

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

TRIP_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "response": {"type": "string", "description": "User-facing answer; for a full itinerary include Daily Summary, Daily Details, and Budget in that order."},
        "total_cost": {"type": "number"},
        "remaining": {"type": "number"},
        "within_budget": {"type": "boolean"},
        "total_budget": {
            "type": "number"
        },
        "currency": {
            "type": "string"
        },
        "costs": {
            "type": "object",
            "properties": {
                "flight": {"type": "number"},
                "hotel": {"type": "number"},
                "food": {"type": "number"},
                "transportation": {"type": "number"},
                "activities": {"type": "number"},
                "other": {"type": "number"}
            },
            "required": [
                "flight",
                "hotel",
                "food",
                "transportation",
                "activities",
                "other"
            ],
            "additionalProperties": False
        }
    },
    "required": [
        "response",
        "total_cost",
        "remaining",
        "within_budget",
        "total_budget",
        "currency",
        "costs"
    ],
    "additionalProperties": False
}

def run_agent(prompt, max_rounds=8, history=None, max_budget_replans=2):
    if max_rounds < 1 or max_budget_replans < 0:
        raise ValueError("max_rounds must be positive and max_budget_replans must be nonnegative")
    # Work on a copy so failed turns do not leave incomplete calls in history.
    messages = list(history) if history is not None else []
    messages.append({"role": "user", "content": prompt})
    budget_result = None
    budget_args = None
    needs_budget_replan = False
    failed_budget_checks = 0
    for round_index in range(max_rounds):
        budget_exhausted = needs_budget_replan and (
            failed_budget_checks > max_budget_replans or round_index == max_rounds - 1
        )
        if needs_budget_replan:
            messages.append({
                "role": "developer",
                "content": BUDGET_EXHAUSTED_INSTRUCTIONS if budget_exhausted else BUDGET_REPLAN_INSTRUCTIONS,
            })
        request = {
            "model": "gpt-5.4-mini",
            "instructions": INSTRUCTIONS,
            "tools": TOOLS,
            "input": messages,
        }
        if budget_exhausted:
            request["tool_choice"] = "none"
        elif needs_budget_replan:
            # A failed budget check must lead to another tool round, not a final answer.
            request["tool_choice"] = "required"
        if budget_result is not None:
            request["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "trip_plan",
                    "strict": True,
                    "schema": TRIP_PLAN_SCHEMA
                }
            }
        response = client.responses.create(**request)
        
        messages.extend(response.output)
        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            if needs_budget_replan and not budget_exhausted:
                continue
            if budget_result is None:
                answer = response.output_text
            else:
                answer = json.loads(response.output_text)
                # Use the latest tool calculation rather than model arithmetic.
                answer.update(
                    total_budget=budget_result["budget"],
                    total_cost=budget_result["total_cost"],
                    remaining=budget_result["remaining"],
                    within_budget=budget_result["within_budget"],
                    costs=budget_args["costs"],
                )
            if history is not None:
                history[:] = messages
            return answer

        for call in calls:
            try:
                args = json.loads(call.arguments)
                result = execute_tool(call.name, args)
                output = json.dumps(result, ensure_ascii=False)
                if call.name == "check_budget" and "error" not in result:
                    budget_result = result
                    budget_args = args
                    needs_budget_replan = not result["within_budget"]
                    if needs_budget_replan:
                        failed_budget_checks += 1
            except Exception as exc:
                diagnostic = error_details(exc)
                print(f"[Tool Error] {call.name}: {json.dumps(diagnostic, ensure_ascii=False)}")
                output = json.dumps({
                    "error": f"{call.name} failed. Check tool inputs and configuration.",
                    "tool": call.name,
                    **diagnostic,
                })
            messages.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": output,
            })
    raise RuntimeError("Agent reached the tool calling limit. Please narrow your request.")
