import unittest
from types import SimpleNamespace

from utils.token_usage import token_totals, usage_dict


class TokenUsageTests(unittest.TestCase):
    def test_all_phases_and_reviewer_are_counted_once(self):
        trace = [
            {"event": "intent", "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}},
            {"event": "model_call", "phase": "planner", "usage": {"input_tokens": 20, "output_tokens": 3, "total_tokens": 23}},
            {"event": "model_call", "phase": "memory_summary", "usage": {"input_tokens": 4, "output_tokens": 1}},
            {"event": "model_call", "phase": "memory_selection", "usage": None},
            {"event": "memory_summary", "evicted_user_turns": 1},
        ]
        result = token_totals(trace, {"input_tokens": 5, "output_tokens": 1, "total_tokens": 6})
        self.assertEqual((result["input_tokens"], result["output_tokens"], result["total_tokens"]),
                         (39, 7, 46))
        self.assertEqual(result["calls"], 5)
        self.assertEqual(result["missing_usage_calls"], 1)
        self.assertEqual(result["by_phase"]["reviewer"]["total_tokens"], 6)

    def test_sdk_usage_conversion(self):
        usage = SimpleNamespace(model_dump=lambda: {"input_tokens": 3, "output_tokens": 2,
                                                     "total_tokens": 5})
        self.assertEqual(usage_dict(SimpleNamespace(usage=usage))["total_tokens"], 5)
        self.assertIsNone(usage_dict(SimpleNamespace()))


if __name__ == "__main__":
    unittest.main()
