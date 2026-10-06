"""Independent, tool-free review of a proposed itinerary."""
import json

from instructions import EVALUATOR_INSTRUCTIONS
from utils.multimodal import has_images
from utils.token_usage import usage_dict

SCORE_NAMES = (
    "itinerary_realism", "geographic_efficiency",
    "preference_alignment", "itinerary_quality",
)

EVIDENCE_FIELDS = {
    "error", "flights", "airline", "flight_number", "departure_airport",
    "round_trip_options", "outbound", "return_options", "return_search_status",
    "independent_return_options",
    "arrival_airport", "time", "id", "price", "currency", "layovers",
    "duration", "total_duration", "properties", "name", "hotel_class",
    "rate_per_night", "total_rate", "stay_nights", "full_stay_price", "lowest", "extracted_lowest",
    "before_taxes_fees", "extracted_before_taxes_fees", "overall_rating",
    "budget", "total_cost", "remaining", "within_budget",
}


def compact_evidence(value):
    if isinstance(value, dict):
        return {key: compact_evidence(item) for key, item in value.items()
                if key in EVIDENCE_FIELDS}
    if isinstance(value, list):
        return [compact_evidence(item) for item in value]
    return value


def tool_evidence(trace):
    if trace is None:
        return []
    return [{"tool": item["name"], "args": item.get("args"),
             "result": compact_evidence(item.get("result"))}
            for item in trace if item.get("event") == "tool_call"
            and item.get("name") in {"search_flights", "search_hotels", "check_budget"}]
EVALUATION_SCHEMA = {
    "type": "object",
    "properties": {
        "is_itinerary": {"type": "boolean"},
        "scores": {
            "type": "object",
            "properties": {name: {"type": "number", "minimum": 0, "maximum": 10} for name in SCORE_NAMES},
            "required": list(SCORE_NAMES), "additionalProperties": False,
        },
        "overall_score": {"type": "number", "minimum": 0, "maximum": 10},
        "issues": {"type": "array", "items": {"type": "string"}},
        "suggestions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["is_itinerary", "scores", "overall_score", "issues", "suggestions"],
    "additionalProperties": False,
}


def evaluate_itinerary(client, conversation, answer, trace=None, memory_context=None):
    # Send user requirements, rather than planner tool calls or internal feedback.
    requirements = [message["content"] for message in conversation
                    if isinstance(message, dict) and message.get("role") == "user"]
    review_data = {"user_requirements": requirements, "candidate": answer,
                   "tool_evidence": tool_evidence(trace)}
    if memory_context is not None:
        review_data["trip_memory"] = memory_context
    evaluation_input = json.dumps(review_data, ensure_ascii=False)
    if has_images(conversation):
        evaluation_input = [m for m in conversation if isinstance(m, dict) and m.get("role") == "user"]
        evaluation_input = evaluation_input + [{"role": "user", "content": (
            "Evaluate this proposed answer against the preceding requirements and reference images:\n"
            + json.dumps({"candidate": answer, "tool_evidence": tool_evidence(trace),
                          "trip_memory": memory_context}, ensure_ascii=False))}]
    response = client.responses.create(
        model="gpt-5.4-mini",
        instructions=EVALUATOR_INSTRUCTIONS,
        input=evaluation_input,
        text={"format": {"type": "json_schema", "name": "itinerary_evaluation",
                         "strict": True, "schema": EVALUATION_SCHEMA}},
    )
    if trace is not None:
        trace.append({"event": "model_call", "phase": "evaluator",
                      "usage": usage_dict(response)})
    evaluation = json.loads(response.output_text)
    if not evaluation.pop("is_itinerary"):
        return None
    scores = evaluation["scores"]
    if any(not isinstance(scores[name], (int, float)) or not 0 <= scores[name] <= 10
           for name in SCORE_NAMES):
        raise ValueError("Evaluator scores must be between 0 and 10")
    evaluation["overall_score"] = sum(scores[name] for name in SCORE_NAMES) / len(SCORE_NAMES)
    return evaluation
