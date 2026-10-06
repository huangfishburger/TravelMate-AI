"""Normalize API usage and aggregate model calls without estimating missing tokens."""

from collections import defaultdict


def usage_dict(response):
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    if isinstance(usage, dict):
        return usage
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    return {key: getattr(usage, key, None) for key in
            ("input_tokens", "output_tokens", "total_tokens")}


def token_totals(trace, reviewer_usage=None):
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
              "calls": 0, "missing_usage_calls": 0, "by_phase": {}}
    calls = [(event.get("phase", "intent"), event.get("usage")) for event in trace
             if event.get("event") in {"model_call", "intent"}]
    if reviewer_usage is not None:
        calls.append(("reviewer", reviewer_usage))
    phases = defaultdict(lambda: {"input_tokens": 0, "output_tokens": 0,
                                  "total_tokens": 0, "calls": 0, "missing_usage_calls": 0})
    for phase, usage in calls:
        bucket = phases[phase]
        for target in (totals, bucket):
            target["calls"] += 1
            if not isinstance(usage, dict):
                target["missing_usage_calls"] += 1
                continue
            for key in ("input_tokens", "output_tokens"):
                target[key] += usage.get(key) or 0
            target["total_tokens"] += usage.get("total_tokens") or (
                (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0))
    totals["by_phase"] = dict(phases)
    return totals
