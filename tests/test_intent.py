import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import agent
from intent import classify_intent


class IntentTests(unittest.TestCase):
    def test_chinese_itinerary_forces_chinese_planner_output(self):
        reply = SimpleNamespace(output=[], output_text="行程摘要\n第一天：東京散步")
        with patch.object(agent, "classify_intent", return_value={"intent": "itinerary",
             "total_budget": None, "currency": None}), \
             patch.object(agent, "evaluate_itinerary", return_value=None), \
             patch.object(agent.client.responses, "create", return_value=reply) as create:
            agent.run_agent("幫我安排東京三天行程")
        self.assertIn("Write the entire user-facing answer in Traditional Chinese",
                      create.call_args.kwargs["instructions"])
        self.assertIn("行程摘要、每日細節、預算", create.call_args.kwargs["instructions"])

    def test_explicit_chinese_preference_survives_english_followup(self):
        history = [{"role": "user", "content": "之後請用中文回答"}]
        self.assertEqual(agent.preferred_response_language("Plan a Tokyo trip", history),
                         "Traditional Chinese")

    def test_english_latest_request_wins_over_earlier_chinese_chat(self):
        history = [{"role": "user", "content": "幫我規劃東京行程"}]
        self.assertEqual(agent.preferred_response_language(
            "Plan a three-day trip to Seattle in English", history), "English")

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

    def test_missing_date_is_not_a_clarification(self):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(output_text=json.dumps({
            "intent": "itinerary", "total_budget": None, "currency": None,
            "needs_clarification": True, "ambiguities": ["Departure date missing"],
            "clarification_question": "你預計什麼時候出發？", "clarification_reason": "conflict",
            "new_trip": False, "state_changes": []}))
        messages = [{"role": "assistant", "content": "你預計什麼時候出發去東京？"},
                    {"role": "user", "content": "不確定"}]
        result = classify_intent(client, messages)
        self.assertFalse(result["needs_clarification"])
        self.assertIsNone(result["clarification_question"])
        self.assertIn("Missing information by itself is not a conflict",
                      client.responses.create.call_args.kwargs["instructions"])


if __name__ == "__main__":
    unittest.main()
