"""Batch execution with incremental JSONL results and fingerprinted resume."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.case_checks import check_rules, result_status


def fingerprint(case, config):
    source = "".join((ROOT / p).read_text(encoding="utf-8") for p in
                     ["agent.py", "evaluator.py", "intent.py", "multimodal.py", "instructions.py", "utils/tool_output.py", "tests/case_checks.py", "tests/reviewer.py", "tests/run_cases.py"])
    return hashlib.sha256((json.dumps({"case": case, "config": config}, sort_keys=True)
                           + source).encode()).hexdigest()


def load_results(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_case(case, config, runner, reviewer=None):
    trace = []
    started = time.perf_counter()
    result = {"case_id": case["id"], "category": case["category"],
              "prompt": case["prompt"], "expected": case["expected"],
              "fingerprint": fingerprint(case, config), "config": config}
    try:
        planner_config = {k: v for k, v in config.items() if k not in {"reviewer_model", "reviewer_enabled"}}
        answer = runner(case["prompt"], trace=trace, **planner_config)
        checks = check_rules(case["expected"], answer, trace)
        result.update(answer=answer, rule_checks=checks, status=result_status(checks), error=None)
    except Exception as exc:
        result.update(answer=None, rule_checks=[], status="error",
                      error={"type": type(exc).__name__, "message": str(exc)})
    evaluations = [e["evaluation"] for e in trace if e["event"] == "evaluation"]
    result.update(trace=trace, evaluation_history=evaluations,
                  quality_replans=sum(e["event"] == "quality_replan" for e in trace),
                  budget_replans=sum(e["event"] == "budget_replan" for e in trace),
                  semantic_review={"status": "pending_manual_review"},
                  quality_target_met=(evaluations[-1]["overall_score"] >= config["evaluation_threshold"]
                                      if evaluations and evaluations[-1] is not None else None),
                  elapsed_seconds=round(time.perf_counter() - started, 3))
    if reviewer is not None and result["error"] is None:
        try:
            review = reviewer(case, result["answer"], trace, result["rule_checks"])
            result["semantic_review"] = review
            result["status"] = review["status"]
        except Exception as exc:
            result["semantic_review"] = {"status": "error", "error": {"type": type(exc).__name__, "message": str(exc)}}
            result["status"] = "fail" if result["status"] == "fail" else "needs_review"
    result["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=ROOT / "tests/test_case.json")
    parser.add_argument("--output", type=Path, default=ROOT / "tests/results/live.jsonl")
    parser.add_argument("--ids", nargs="+", type=int)
    parser.add_argument("--category")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--execute", action="store_true", help="Run real model and search API calls; otherwise only list cases")
    parser.add_argument("--threshold", type=float, default=7)
    parser.add_argument("--quality-replans", type=int, default=2)
    parser.add_argument("--reviewer-model", default="gpt-5.4-mini")
    parser.add_argument("--no-reviewer", action="store_true")
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    cases = [c for c in cases if (not args.ids or c["id"] in args.ids)
             and (not args.category or c["category"] == args.category)]
    config = {"evaluation_threshold": args.threshold, "max_quality_replans": args.quality_replans,
              "reviewer_model": args.reviewer_model, "reviewer_enabled": not args.no_reviewer}
    if not args.execute:
        print(json.dumps({"mode": "list_only", "case_ids": [c["id"] for c in cases], "config": config}))
        return
    previous = load_results(args.output) if args.resume else []
    latest = {r["fingerprint"]: r for r in previous}
    completed = {key for key, r in latest.items() if r["status"] != "error"
                 and r.get("semantic_review", {}).get("status") != "error"}
    from agent import run_agent, client
    from tests.reviewer import review_case
    reviewer = None if args.no_reviewer else lambda case, answer, trace, checks: review_case(
        client, case, answer, trace, checks, model=args.reviewer_model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    results = []
    with args.output.open("a" if args.resume else "w", encoding="utf-8") as output:
        for case in cases:
            key = fingerprint(case, config)
            if key in completed:
                results.append(latest[key])
                continue
            result = run_case(case, config, run_agent, reviewer=reviewer)
            output.write(json.dumps(result, ensure_ascii=False) + "\n")
            output.flush()
            results.append(result)
            print(f"Case {case['id']}: {result['status']} ({result['elapsed_seconds']}s)", flush=True)
    summary = {"total": len(results), "statuses": dict(Counter(r["status"] for r in results)),
               "quality_target_met": sum(r["quality_target_met"] is True for r in results),
               "quality_evaluated": sum(r["quality_target_met"] is not None for r in results)}
    args.output.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
