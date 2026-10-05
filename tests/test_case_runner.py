import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from tests.case_checks import check_rules, result_status
from tests.run_cases import fingerprint, load_results, run_case

CASES = json.loads(Path(__file__).with_name("test_case.json").read_text(encoding="utf-8"))
CONFIG = {"evaluation_threshold": 7, "max_quality_replans": 2}


class CaseRunnerTests(unittest.TestCase):
    def test_intent_clarification_budget_check_is_not_applicable(self):
        checks = check_rules(CASES[0]["expected"], "Nov 6-8 or Nov 6-9?", [
            {"event": "clarification", "answer": "Nov 6-8 or Nov 6-9?"},
            {"event": "final", "answer": "Nov 6-8 or Nov 6-9?"},
        ])
        budget = next(c for c in checks if c["name"] == "final_itinerary_budget_check")
        self.assertEqual(budget["status"], "not_applicable")
        self.assertEqual(result_status([budget]), "pass")

    def test_forbidden_budget_call_fails_simple_query(self):
        trace = [{"event": "tool_call", "name": "check_budget", "attempt": 0,
                  "args": {"total_budget": 100, "costs": {"flight": 80}},
                  "result": {"budget": 100, "total_cost": 80, "remaining": 20, "within_budget": True}}]
        self.assertEqual(result_status(check_rules(CASES[45]["expected"], "Flights", trace)), "fail")

    def test_insufficient_evidence_needs_review(self):
        self.assertEqual(result_status(check_rules(CASES[45]["expected"], "Flights", [])), "needs_review")

    def test_error_preserves_partial_trace(self):
        def runner(prompt, trace, **config):
            trace.append({"event": "planner_start", "attempt": 0})
            raise RuntimeError("fixture failure")
        result = run_case(CASES[0], CONFIG, runner)
        self.assertEqual(result["status"], "error")
        self.assertEqual(len(result["trace"]), 1)

    def test_fingerprint_changes_when_expectations_change(self):
        case = dict(CASES[0], expected={})
        self.assertNotEqual(fingerprint(case, CONFIG), fingerprint(CASES[0], CONFIG))

    def test_jsonl_reload(self):
        path = Mock()
        path.exists.return_value = True
        path.read_text.return_value = '{"case_id": 1}\n{"case_id": 2}\n'
        self.assertEqual(len(load_results(path)), 2)


if __name__ == "__main__":
    unittest.main()
