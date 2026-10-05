import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import agent
from intent import classify_intent


class IntentTests(unittest.TestCase):
    def test_clarification_skips_planning_tools_and_evaluator(self):
        history = []
        trace = []
        intent = {"intent": "itinerary", "total_budget": 1000, "currency": "USD",
                  "needs_clarification": True, "ambiguities": ["Conflicting day count and dates"],
                  "clarification_question": "Nov 6-8 or Nov 6-9?"}
        with patch.object(agent, "classify_intent", return_value=intent), \
                patch.object(agent, "_run_planner") as planner, \
                patch.object(agent, "evaluate_itinerary") as evaluator:
            answer = agent.run_agent("Three days Nov 6-9", history=history, trace=trace)
        self.assertEqual(answer, intent["clarification_question"])
        planner.assert_not_called()
        evaluator.assert_not_called()
        self.assertEqual(history[-1], {"role": "assistant", "content": answer})
        self.assertTrue(any(e["event"] == "clarification" for e in trace))

    def test_followup_resolution_and_prior_question_are_supplied(self):
        client = Mock()
        intent = {"intent": "itinerary", "total_budget": 1000, "currency": "USD",
                  "needs_clarification": False, "ambiguities": [], "clarification_question": None}
        client.responses.create.return_value = SimpleNamespace(output_text=json.dumps(intent))
        conversation = [{"role": "user", "content": "Three days Nov 6-9, budget 1000"},
                        {"role": "assistant", "content": "Nov 6-8 or Nov 6-9?"},
                        {"role": "user", "content": "Use Nov 6-9, four days"}]
        self.assertFalse(classify_intent(client, conversation)["needs_clarification"])
        self.assertEqual(json.loads(client.responses.create.call_args.kwargs["input"]), conversation)

    def test_empty_clarification_question_is_rejected(self):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(output_text=json.dumps({
            "needs_clarification": True, "clarification_question": " "}))
        with self.assertRaisesRegex(ValueError, "nonempty question"):
            classify_intent(client, [])


if __name__ == "__main__":
    unittest.main()
