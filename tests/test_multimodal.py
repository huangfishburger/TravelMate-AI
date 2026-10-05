import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import agent
from intent import classify_intent
from evaluator import evaluate_itinerary
from multimodal import user_content, image_part


class MultimodalTests(unittest.TestCase):
    def test_text_only_unchanged_and_local_image_encoded(self):
        self.assertEqual(user_content("Hello"), "Hello")
        with patch("multimodal.Path.read_bytes", return_value=b"\x89PNG\r\n\x1a\nfixture"):
            content = user_content("Where is this?", ["photo.png"])
        self.assertEqual(content[0]["text"], "Where is this?")
        self.assertTrue(content[1]["image_url"].startswith("data:image/png;base64,"))

    def test_invalid_image_rejected(self):
        with patch("multimodal.Path.read_bytes", return_value=b"not an image"):
            with self.assertRaises(ValueError):
                image_part("bad.png")

    def test_intent_receives_actual_image_content(self):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(output_text=json.dumps({
            "intent": "simple_query", "total_budget": None, "currency": None,
            "needs_clarification": False, "ambiguities": [], "clarification_question": None}))
        messages = [{"role": "user", "content": user_content("This flight", ["https://example.com/flight.png"])}]
        classify_intent(client, messages)
        self.assertEqual(client.responses.create.call_args.kwargs["input"], messages)

    def test_planner_receives_image_and_history_preserves_it(self):
        history = []
        intent = {"intent": "simple_query", "total_budget": None, "currency": None}
        response = SimpleNamespace(output=[], output_text="Likely a coastal viewpoint.")
        with patch.object(agent, "classify_intent", return_value=intent), \
                patch.object(agent.client.responses, "create", return_value=response) as create, \
                patch.object(agent, "evaluate_itinerary", return_value=None):
            agent.run_agent("Where?", images=["https://example.com/photo.png"], history=history)
        content = create.call_args.kwargs["input"][0]["content"]
        self.assertEqual(content[1]["type"], "input_image")
        self.assertEqual(history[0]["content"], content)

    def test_evaluator_can_see_reference_image(self):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(output_text=json.dumps({"is_itinerary": False}))
        messages = [{"role": "user", "content": user_content("Similar scenery", ["https://example.com/photo.png"])}]
        self.assertIsNone(evaluate_itinerary(client, messages, "Recommendations"))
        self.assertEqual(client.responses.create.call_args.kwargs["input"][0], messages[0])


if __name__ == "__main__":
    unittest.main()
