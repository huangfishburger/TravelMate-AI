import json
import unittest
from unittest.mock import Mock, patch

import agent
from memory import apply_changes, compact_history, new_memory


def change(path, value, action="set"):
    return {"path": path, "action": action, "value_json": json.dumps(value)}


class MemoryTests(unittest.TestCase):
    def test_updates_removals_and_locked_selection(self):
        state = new_memory()["trip_state"]
        apply_changes(state, [change("destination", "Seattle"),
                              change("hard_constraints.budget", 1000),
                              change("locked.flight", True),
                              change("selected.flight", {"number": "AS1"})], "user")
        apply_changes(state, [change("selected.flight", {"number": "AS2"})], "plan")
        self.assertEqual(state["selected"]["flight"]["number"], "AS1")
        apply_changes(state, [change("hard_constraints.budget", None, "remove"),
                              change("locked.flight", None, "remove")], "user")
        self.assertIsNone(state["hard_constraints"]["budget"])
        self.assertFalse(state["locked"]["flight"])

    def test_traveler_count_is_stored_and_validated(self):
        state = new_memory()["trip_state"]
        apply_changes(state, [change("travelers", 2)], "user")
        self.assertEqual(state["travelers"], 2)
        with self.assertRaisesRegex(ValueError, "positive integer"):
            apply_changes(state, [change("travelers", 0)], "user")

    def test_only_five_recent_turns_remain(self):
        history = []
        for n in range(7):
            history.extend([{"role": "user", "content": f"request {n}"},
                            {"role": "assistant", "content": f"answer {n}"}])
        client = Mock()
        client.responses.create.return_value.output_text = '{"summary":"earlier requests"}'
        memory = new_memory()
        compact_history(client, history, memory)
        self.assertEqual(memory["summary"], "earlier requests")
        self.assertEqual(sum(m["role"] == "user" for m in history), 5)
        self.assertEqual(history[0]["content"], "request 2")

    def test_user_update_reaches_planner_and_next_turn(self):
        memory, history = new_memory(), []
        intents = [
            {"intent": "simple_query", "total_budget": None, "currency": None,
             "needs_clarification": False, "travelers": 2,
             "state_changes": [change("destination", "Seattle"), change("travelers", 2)]},
            {"intent": "simple_query", "total_budget": None, "currency": None,
             "needs_clarification": False, "travelers": None,
             "state_changes": [change("soft_preferences.pace", "relaxed")]},
        ]
        def planner(*args, **kwargs):
            self.assertEqual(kwargs["memory_context"]["trip_state"]["destination"], "Seattle")
            self.assertEqual(kwargs["intent"]["travelers"], 2)
            return "Done"
        with patch.object(agent, "classify_intent", side_effect=intents), \
             patch.object(agent, "_run_planner", side_effect=planner), \
             patch.object(agent, "evaluate_itinerary", return_value=None):
            agent.run_agent("Seattle", history=history, memory=memory)
            agent.run_agent("Relaxed please", history=history, memory=memory)
        self.assertEqual(memory["trip_state"]["soft_preferences"]["pace"], "relaxed")


if __name__ == "__main__":
    unittest.main()
