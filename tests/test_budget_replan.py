"""Budget retry control flow checks without network calls."""
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent
from utils.budget import check_budget


def tool_response(name, args):
    return SimpleNamespace(output=[SimpleNamespace(
        type="function_call", name=name, arguments=json.dumps(args), call_id=name,
    )], output_text="")


class BudgetReplanTests(unittest.TestCase):
    def setUp(self):
        intent_patch = patch.object(agent, "classify_intent", return_value={"intent": "itinerary", "total_budget": 100, "currency": "USD"})
        intent_patch.start()
        self.addCleanup(intent_patch.stop)
        evaluator_patch = patch.object(agent, "evaluate_itinerary", return_value=None)
        evaluator_patch.start()
        self.addCleanup(evaluator_patch.stop)

    def test_missing_budget_check_forces_check_before_return(self):
        draft = SimpleNamespace(output=[], output_text=json.dumps({
            "response_type": "itinerary", "response": "Unchecked plan"}))
        check = tool_response("check_budget", {"total_budget": 100, "costs": {"hotel": 80}})
        final = SimpleNamespace(output=[], output_text=json.dumps({"response": "Checked plan"}))
        trace = []
        with patch.object(agent.client.responses, "create", side_effect=[draft, check, final]) as create, \
                patch.object(agent, "execute_tool", side_effect=lambda name, args: check_budget(**args)):
            answer = agent.run_agent("Plan within 100", trace=trace)
        self.assertTrue(answer["within_budget"])
        self.assertEqual(create.call_args_list[1].kwargs["tool_choice"],
                         {"type": "function", "name": "check_budget"})
        self.assertTrue(any(e["event"] == "budget_check_missing" for e in trace))

    def test_clarification_can_return_without_budget_check(self):
        response = SimpleNamespace(output=[], output_text=json.dumps({
            "response_type": "clarification", "response": "Which dates?"}))
        with patch.object(agent.client.responses, "create", return_value=response), \
                patch.object(agent, "execute_tool") as execute:
            self.assertEqual(agent.run_agent("Plan within 100"), "Which dates?")
        execute.assert_not_called()

    def test_category_cap_does_not_require_budget_check(self):
        response = SimpleNamespace(output=[], output_text="Hotel search results")
        with patch.object(agent, "classify_intent", return_value={"intent": "simple_query", "total_budget": None, "currency": "USD"}), \
                patch.object(agent.client.responses, "create", return_value=response) as create:
            self.assertEqual(agent.run_agent("Hotels under 100 per night"), "Hotel search results")
        self.assertNotIn("text", create.call_args.kwargs)

    def test_missing_check_never_returns_unchecked_plan_at_limit(self):
        response = SimpleNamespace(output=[], output_text=json.dumps({
            "response_type": "itinerary", "response": "Unchecked plan"}))
        with patch.object(agent.client.responses, "create", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "tool calling limit"):
                agent.run_agent("Plan within 100", max_rounds=1)

    def test_over_budget_requires_tools_until_recheck_passes(self):
        final = SimpleNamespace(output=[], output_text=json.dumps({"response": "Revised plan"}))
        responses = [
            tool_response("check_budget", {"total_budget": 100, "costs": {"hotel": 120}}),
            tool_response("search_hotels", {}),
            tool_response("check_budget", {"total_budget": 100, "costs": {"hotel": 80}}),
            final,
        ]
        def execute(name, args):
            return check_budget(**args) if name == "check_budget" else {"price": 80}
        trace = []
        with patch.object(agent.client.responses, "create", side_effect=responses) as create, \
                patch.object(agent, "execute_tool", side_effect=execute):
            answer = agent.run_agent("Plan within 100", trace=trace)
        self.assertTrue(answer["within_budget"])
        self.assertEqual(answer["total_cost"], 80)
        requests = create.call_args_list
        self.assertEqual(requests[1].kwargs["tool_choice"], "required")
        self.assertEqual(requests[2].kwargs["tool_choice"], "required")
        self.assertNotIn("tool_choice", requests[3].kwargs)
        self.assertEqual(sum(e["event"] == "budget_replan" for e in trace), 1)
        self.assertEqual(sum(e["event"] == "tool_call" for e in trace), 3)
        self.assertEqual(trace[-1]["event"], "final")

    def test_persistent_over_budget_returns_explanation_after_two_replans(self):
        response = tool_response("check_budget", {"total_budget": 100, "costs": {"hotel": 120}})
        final = SimpleNamespace(output=[], output_text=json.dumps({"response": "No plan found within budget; shortfall 20."}))
        with patch.object(agent.client.responses, "create", side_effect=[response, response, response, final]) as create, \
                patch.object(agent, "execute_tool", side_effect=lambda name, args: check_budget(**args)):
            answer = agent.run_agent("Plan within 100")
        self.assertFalse(answer["within_budget"])
        self.assertEqual(answer["remaining"], -20)
        self.assertEqual(create.call_args_list[-1].kwargs["tool_choice"], "none")
        self.assertEqual(create.call_args_list[-1].kwargs["input"][-1]["content"], agent.BUDGET_EXHAUSTED_INSTRUCTIONS)

    def test_last_available_round_explains_over_budget(self):
        response = tool_response("check_budget", {"total_budget": 100, "costs": {"hotel": 120}})
        final = SimpleNamespace(output=[], output_text=json.dumps({"response": "Budget shortfall 20."}))
        with patch.object(agent.client.responses, "create", side_effect=[response, final]) as create, \
                patch.object(agent, "execute_tool", side_effect=lambda name, args: check_budget(**args)):
            answer = agent.run_agent("Plan within 100", max_rounds=2)
        self.assertFalse(answer["within_budget"])
        self.assertEqual(create.call_args_list[-1].kwargs["tool_choice"], "none")


if __name__ == "__main__":
    unittest.main()
