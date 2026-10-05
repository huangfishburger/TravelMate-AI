import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import agent
from evaluator import evaluate_itinerary, SCORE_NAMES


def review(score):
    return {"scores": {name: score for name in SCORE_NAMES},
            "overall_score": score, "issues": ["Day 2 has excessive travel."],
            "suggestions": ["Group nearby stops on Day 2."]}


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        intent_patch = patch.object(agent, "classify_intent", return_value={
            "intent": "itinerary", "total_budget": None, "currency": None})
        self.intent_mock = intent_patch.start()
        self.addCleanup(intent_patch.stop)

    def test_passing_score_does_not_replan(self):
        with patch.object(agent, "_run_planner", return_value="Itinerary") as planner, \
                patch.object(agent, "evaluate_itinerary", return_value=review(7)):
            result = agent.run_agent("Plan a trip")
        self.assertEqual(planner.call_count, 1)
        self.assertEqual(result["evaluation"]["overall_score"], 7)

    def test_two_replans_then_returns_latest_even_if_low(self):
        with patch.object(agent, "_run_planner", side_effect=["First", "Second", "Third"]) as planner, \
                patch.object(agent, "evaluate_itinerary", return_value=review(6)) as evaluator:
            result = agent.run_agent("Plan a trip")
        self.assertEqual(planner.call_count, 3)
        self.assertEqual(evaluator.call_count, 3)
        self.assertEqual(self.intent_mock.call_count, 1)
        intents = [call.kwargs["intent"] for call in planner.call_args_list]
        self.assertTrue(all(intent is intents[0] for intent in intents))
        self.assertEqual(result["response"], "Third")
        self.assertEqual(result["evaluation"]["overall_score"], 6)
        self.assertIn("Group nearby stops", planner.call_args.args[2][-1]["content"])

    def test_stops_when_revision_passes(self):
        with patch.object(agent, "_run_planner", side_effect=["First", "Better"]) as planner, \
                patch.object(agent, "evaluate_itinerary", side_effect=[review(6), review(8)]):
            result = agent.run_agent("Plan a trip")
        self.assertEqual(planner.call_count, 2)
        self.assertEqual(result["response"], "Better")

    def test_non_itinerary_keeps_original_response(self):
        with patch.object(agent, "_run_planner", return_value="Which city?"), \
                patch.object(agent, "evaluate_itinerary", return_value=None):
            self.assertEqual(agent.run_agent("Plan a trip"), "Which city?")

    def test_average_calculated_by_code_and_prior_preferences_supplied(self):
        client = Mock()
        evaluation = review(8)
        evaluation.update(is_itinerary=True, overall_score=1)
        client.responses.create.return_value = SimpleNamespace(output_text=json.dumps(evaluation))
        result = evaluate_itinerary(client, [{"role": "user", "content": "I like nature"}], "Plan")
        self.assertEqual(result["overall_score"], 8)
        self.assertIn("I like nature", client.responses.create.call_args.kwargs["input"])

    def test_tool_prices_reach_evaluator_without_image_metadata(self):
        client = Mock()
        evaluation = review(7)
        evaluation["is_itinerary"] = True
        client.responses.create.return_value = SimpleNamespace(output_text=json.dumps(evaluation))
        trace = [{"event": "tool_call", "name": "search_flights",
                  "args": {"origin": "LAX", "destination": "SFO"},
                  "result": {"flights": [{"price": 104, "flights": [{"airline": "Frontier"}],
                                          "airline_logo": "large-image-url"}]}}]
        evaluate_itinerary(client, [{"role": "user", "content": "Two travelers"}], "Flight $104 total", trace)
        payload = json.loads(client.responses.create.call_args.kwargs["input"])
        self.assertEqual(payload["tool_evidence"][0]["result"]["flights"][0]["price"], 104)
        self.assertNotIn("airline_logo", payload["tool_evidence"][0]["result"]["flights"][0])


if __name__ == "__main__":
    unittest.main()
