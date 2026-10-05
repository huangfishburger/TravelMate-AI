import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import agent
from utils.tool_output import compact_tool_result


class ToolOutputTests(unittest.TestCase):
    def test_compacts_search_metadata_but_keeps_all_options(self):
        result = {"flights": [{"price": i, "flights": [{"airline": "Alaska",
                  "departure_airport": {"id": "SAN", "time": "06:00"}}],
                  "airline_logo": "large-url", "departure_token": "large-token"}
                  for i in range(15)], "search_metadata": {"id": "metadata"}}
        compact = compact_tool_result(result, "search_flights")
        self.assertEqual(len(compact["flights"]), 15)
        self.assertEqual(compact["flights"][0]["flights"][0]["departure_airport"]["id"], "SAN")
        self.assertNotIn("departure_token", compact["flights"][0])
        self.assertNotIn("search_metadata", compact)
        self.assertIn("departure_token", result["flights"][0])

    def test_history_is_compact_and_trace_keeps_raw_result(self):
        raw = {"properties": [{"name": "Hotel", "total_rate": {"extracted_lowest": 300},
                               "images": ["large-image-url"]}],
               "search_metadata": {"id": "metadata"}}
        call = SimpleNamespace(type="function_call", name="search_hotels",
                               arguments="{}", call_id="hotel-1")
        responses = [SimpleNamespace(output=[call], output_text=""),
                     SimpleNamespace(output=[], output_text="Hotel option")]
        trace, history = [], []
        with patch.object(agent, "classify_intent", return_value={"intent": "simple_query", "total_budget": None}), \
                patch.object(agent.client.responses, "create", side_effect=responses), \
                patch.object(agent, "execute_tool", return_value=raw), \
                patch.object(agent, "evaluate_itinerary", return_value=None):
            agent.run_agent("Find a hotel", trace=trace, history=history)
        output = next(m for m in history if isinstance(m, dict) and m.get("type") == "function_call_output")
        self.assertNotIn("search_metadata", json.loads(output["output"]))
        self.assertEqual(next(e for e in trace if e["event"] == "tool_call")["result"], raw)


if __name__ == "__main__":
    unittest.main()
