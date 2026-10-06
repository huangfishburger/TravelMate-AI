"""Read-only checks available to the itinerary evaluator agent."""

from utils.budget import check_budget


def audit_budget(answer, trace):
    """Recalculate the candidate's structured costs and compare its budget check."""
    if not isinstance(answer, dict):
        return {"status": "unavailable", "reason": "Candidate has no structured costs"}
    costs = answer.get("costs")
    budget = answer.get("total_budget")
    if not isinstance(costs, dict) or not isinstance(budget, (int, float)) or isinstance(budget, bool):
        return {"status": "unavailable", "reason": "Candidate has no structured budget"}
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in costs.values()):
        return {"status": "invalid", "reason": "Cost categories must contain numbers"}
    recalculated = check_budget(budget, costs, answer.get("currency"))
    mismatches = []
    for key in ("total_cost", "remaining"):
        claimed = answer.get(key)
        if not isinstance(claimed, (int, float)) or abs(claimed - recalculated[key]) > 0.01:
            mismatches.append(key)
    if answer.get("within_budget") is not recalculated["within_budget"]:
        mismatches.append("within_budget")
    checks = [item for item in (trace or []) if item.get("event") == "tool_call"
              and item.get("name") == "check_budget" and isinstance(item.get("result"), dict)
              and "error" not in item["result"]]
    last_check = checks[-1] if checks else None
    if last_check is None:
        mismatches.append("missing_check_budget")
    else:
        args = last_check.get("args") or {}
        if args.get("total_budget") != budget or args.get("costs") != costs:
            mismatches.append("different_budget_check_inputs")
        if args.get("currency") != answer.get("currency"):
            mismatches.append("different_budget_check_currency")
    return {"status": "pass" if not mismatches else "mismatch",
            "recalculated": recalculated, "mismatches": mismatches,
            "note": "This checks arithmetic and tool inputs, not whether prices cover every traveler or night."}


def inspect_booking_evidence(trace):
    """Summarize searched flight times and full-stay hotel prices for review."""
    flights, hotels = [], []
    for item in trace or []:
        if item.get("event") != "tool_call":
            continue
        result = item.get("result") or {}
        if not isinstance(result, dict):
            continue
        if item.get("name") == "search_flights":
            def flight(option):
                legs = option.get("flights") or []
                first, last = (legs[0], legs[-1]) if legs else ({}, {})
                return {"departure": (first.get("departure_airport") or {}).get("time"),
                        "arrival": (last.get("arrival_airport") or {}).get("time"),
                        "origin": (first.get("departure_airport") or {}).get("id"),
                        "destination": (last.get("arrival_airport") or {}).get("id"),
                        "price": option.get("price"), "segments": len(legs)}
            flights.append({"query": item.get("args"), "error": result.get("error"),
                            "outbound": [flight(x) for x in result.get("flights", [])[:5]],
                            "paired_returns": [{"outbound": flight(pair.get("outbound") or {}),
                                                "returns": [flight(x) for x in pair.get("return_options", [])[:5]]}
                                               for pair in result.get("round_trip_options", [])[:5]],
                            "independent_returns": [flight(x) for x in result.get("independent_return_options", [])[:5]]})
        elif item.get("name") == "search_hotels":
            hotels.append({"query": item.get("args"), "currency": result.get("currency"),
                           "stay_nights": result.get("stay_nights"), "error": result.get("error"),
                           "properties": [{"name": prop.get("name"),
                                           "full_stay_price": prop.get("full_stay_price"),
                                           "total_rate": prop.get("total_rate"),
                                           "rate_per_night": prop.get("rate_per_night")}
                                          for prop in result.get("properties", [])[:10]
                                          if isinstance(prop, dict)]})
    return {"flights": flights, "hotels": hotels}
