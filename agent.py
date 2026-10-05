import json
import os
from copy import deepcopy

from dotenv import load_dotenv
from openai import OpenAI

from instructions import INSTRUCTIONS, BUDGET_REPLAN_INSTRUCTIONS, BUDGET_EXHAUSTED_INSTRUCTIONS
from instructions import QUALITY_REPLAN_INSTRUCTIONS
from evaluator import evaluate_itinerary
from intent import classify_intent
from multimodal import user_content
from tools.registry import TOOLS, execute_tool
from utils.errors import error_details
from utils.tool_output import compact_tool_result

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

def run_agent(prompt, max_rounds=8, history=None, max_budget_replans=2,
              evaluation_threshold=7, max_quality_replans=2, trace=None, images=None):
    if not 0 <= evaluation_threshold <= 10 or max_quality_replans < 0:
        raise ValueError("Invalid evaluation threshold or quality replan limit")
    # Commit conversation only after the entire planning and review pipeline succeeds.
    working_history = list(history) if history is not None else []
    content = user_content(prompt, images)
    intent = classify_intent(client, working_history + [{"role": "user", "content": content}], trace=trace)
    if intent.get("needs_clarification", False):
        answer = intent["clarification_question"]
        working_history.extend([
            {"role": "user", "content": content},
            {"role": "assistant", "content": answer},
        ])
        if history is not None:
            history[:] = working_history
        record_trace(trace, "clarification", answer=answer, ambiguities=intent["ambiguities"])
        record_trace(trace, "final", answer=answer)
        return answer
    for attempt in range(max_quality_replans + 1):
        record_trace(trace, "planner_start", attempt=attempt)
        answer = _run_planner(content if attempt == 0 else None, max_rounds,
                              working_history, max_budget_replans, trace=trace, attempt=attempt, intent=intent)
        record_trace(trace, "candidate", attempt=attempt, answer=answer)
        evaluation = evaluate_itinerary(client, working_history, answer, trace=trace)
        record_trace(trace, "evaluation", attempt=attempt, evaluation=evaluation)
        if evaluation is None or evaluation["overall_score"] >= evaluation_threshold or attempt == max_quality_replans:
            if evaluation is not None:
                answer = dict(answer) if isinstance(answer, dict) else {"response": answer}
                answer["evaluation"] = evaluation
            if history is not None:
                history[:] = working_history
            record_trace(trace, "final", attempt=attempt, answer=answer)
            return answer
        record_trace(trace, "quality_replan", attempt=attempt + 1)
        working_history.append({
            "role": "developer",
            "content": QUALITY_REPLAN_INSTRUCTIONS + "\n" + json.dumps(evaluation, ensure_ascii=False),
        })


def record_trace(trace, event, **data):
    if trace is not None:
        trace.append(deepcopy({"event": event, **data}))


def _run_planner(prompt, max_rounds=8, history=None, max_budget_replans=2,
                 trace=None, attempt=0, intent=None):
    if max_rounds < 1 or max_budget_replans < 0:
        raise ValueError("max_rounds must be positive and max_budget_replans must be nonnegative")
    # Work on a copy so failed turns do not leave incomplete calls in history.
    messages = list(history) if history is not None else []
    if prompt is not None:
        messages.append({"role": "user", "content": prompt})
    if intent is None:
        intent = classify_intent(client, messages, trace=trace)
    budget_required = intent["intent"] in {"itinerary", "budget_check"} and intent["total_budget"] is not None
    force_budget_check = False
    budget_result = None
    budget_args = None
    needs_budget_replan = False
    failed_budget_checks = 0
    budget_replanning = False
    for round_index in range(max_rounds):
        budget_exhausted = needs_budget_replan and (
            failed_budget_checks > max_budget_replans or round_index == max_rounds - 1
        )
        if needs_budget_replan:
            if not budget_exhausted and not budget_replanning:
                record_trace(trace, "budget_replan", attempt=attempt, round=round_index)
                budget_replanning = True
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
        elif force_budget_check:
            request["tool_choice"] = {"type": "function", "name": "check_budget"}
        if budget_result is not None:
            request["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "trip_plan",
                    "strict": True,
                    "schema": TRIP_PLAN_SCHEMA
                }
            }
        elif budget_required:
            request["text"] = {"format": {
                "type": "json_schema", "name": "planning_response", "strict": True,
                "schema": {
                    "type": "object", "properties": {
                        "response_type": {"type": "string", "enum": ["itinerary", "budget_answer", "clarification", "failure_explanation"]},
                        "response": {"type": "string"},
                    }, "required": ["response_type", "response"], "additionalProperties": False,
                },
            }}
        response = client.responses.create(**request)
        usage = getattr(response, "usage", None)
        record_trace(trace, "model_call", phase="planner", attempt=attempt,
                     round=round_index, usage=usage.model_dump() if usage is not None else None)
        
        messages.extend(response.output)
        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            if needs_budget_replan and not budget_exhausted:
                continue
            if budget_result is None:
                if budget_required:
                    draft = json.loads(response.output_text)
                    if draft["response_type"] in {"itinerary", "budget_answer"}:
                        record_trace(trace, "budget_check_missing", attempt=attempt, round=round_index)
                        messages.append({"role": "developer", "content": (
                            "This proposed answer has not been budget-checked and cannot be returned. "
                            "Call check_budget with the costs of this plan in a consistent currency and traveler scope. "
                            f"Preserve the user's total budget: {intent['total_budget']} {intent['currency']}."
                        )})
                        force_budget_check = True
                        continue
                    answer = draft["response"]
                else:
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
            args = None
            result = None
            try:
                args = json.loads(call.arguments)
                if call.name == "check_budget" and budget_required and args.get("total_budget") != intent["total_budget"]:
                    raise ValueError("check_budget must use the user's original total budget")
                result = execute_tool(call.name, args)
                output = json.dumps(compact_tool_result(result, call.name), ensure_ascii=False)
                if call.name == "check_budget" and "error" not in result:
                    budget_replanning = False
                    force_budget_check = False
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
            record_trace(trace, "tool_call", attempt=attempt, round=round_index,
                         name=call.name, args=args,
                         result=result if result is not None else json.loads(output))
            messages.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": output,
            })
    raise RuntimeError("Agent reached the tool calling limit. Please narrow your request.")
