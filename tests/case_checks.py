"""Evidence-based checks. Unknown semantic facts never count as passes."""
from collections import Counter
from math import isclose


def check_rules(expected, answer, trace):
    checks = []

    def add(name, passed, detail):
        checks.append({"name": name, "status": "unknown" if passed is None else "pass" if passed else "fail",
                       "detail": detail})

    tools = [e for e in trace if e["event"] == "tool_call"]
    evaluations = [e for e in trace if e["event"] == "evaluation"]
    clarification_only = any(e["event"] == "clarification" for e in trace) and not any(
        e["event"] == "planner_start" for e in trace)
    is_itinerary = evaluations[-1]["evaluation"] is not None if evaluations else None
    forbidden = expected["tool_behavior"]["forbidden_tools"]
    add("forbidden_tools", not any(e["name"] in forbidden for e in tools), forbidden)
    budget_calls = [e for e in tools if e["name"] == "check_budget" and "error" not in e["result"]]
    if expected["tool_behavior"]["check_budget_required_for_final_itinerary"]:
        final_attempt = next((e["attempt"] for e in reversed(trace) if e["event"] == "planner_start"), 0)
        current_checks = [e for e in budget_calls if e["attempt"] == final_attempt]
        if clarification_only:
            checks.append({"name": "final_itinerary_budget_check", "status": "not_applicable",
                           "detail": "Intent clarification returned before planning; no itinerary requires a budget check."})
        else:
            add("final_itinerary_budget_check", bool(current_checks) if is_itinerary else None,
                "Required for a final budgeted itinerary; other response types need review.")
    original_budget = expected["hard_constraints"].get("total_budget_usd")
    for index, event in enumerate(budget_calls):
        args, result = event["args"], event["result"]
        total = sum(args["costs"].values())
        add(f"budget_arithmetic_{index}",
            isclose(result["total_cost"], total, abs_tol=0.01)
            and isclose(result["remaining"], args["total_budget"] - total, abs_tol=0.01)
            and result["within_budget"] == (total <= args["total_budget"]), result)
        if original_budget is not None:
            add(f"original_budget_{index}", isclose(args["total_budget"], original_budget, abs_tol=0.01), args["total_budget"])
    if isinstance(answer, dict) and budget_calls:
        last = budget_calls[-1]["result"]
        add("returned_budget_matches_tool", all(answer.get(k) == last[k] for k in
            ("total_cost", "remaining", "within_budget")) and answer.get("total_budget") == last["budget"], last)
    quality_replans = sum(e["event"] == "quality_replan" for e in trace)
    add("quality_replan_limit", quality_replans <= expected["quality_behavior"]["max_quality_replans"], quality_replans)
    budget_counts = Counter(e["attempt"] for e in trace if e["event"] == "budget_replan")
    add("budget_replan_limit", all(n <= expected["budget_behavior"]["max_budget_replans_per_planner_run"]
        for n in budget_counts.values()), dict(budget_counts))
    for index, event in enumerate(evaluations):
        evaluation = event["evaluation"]
        if evaluation is not None:
            scores = evaluation["scores"]
            add(f"evaluation_average_{index}", isclose(evaluation["overall_score"],
                sum(scores.values()) / len(scores), abs_tol=1e-8), evaluation["overall_score"])
    if expected["output_behavior"]["must_not_expand_simple_query_to_full_itinerary"]:
        add("simple_query_not_itinerary", None if is_itinerary is None else not is_itinerary,
            "Evaluator classification; manually verify response scope.")
    if expected["hard_constraints"].get("nonstop_required"):
        flights = [e for e in tools if e["name"] == "search_flights"]
        add("nonstop_search_filter", all(e["args"].get("nonstop") is True for e in flights) if flights else None,
            "Search filter alone does not verify the selected flight.")
    add("semantic_requirements", None,
        "Review response type, selected options, dates, traveler scope, hard constraints, soft preferences, estimates, and itinerary sections against expected and tool evidence.")
    return checks


def result_status(checks):
    if any(c["status"] == "fail" for c in checks):
        return "fail"
    if any(c["status"] == "unknown" for c in checks):
        return "needs_review"
    return "pass"
