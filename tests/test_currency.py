import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

from utils.currency import default_currency
from intent import classify_intent
from tools.hotels import search_hotels


class CurrencyTests(unittest.TestCase):
    def test_origin_defaults(self):
        self.assertEqual(default_currency("TPE"), "TWD")
        self.assertEqual(default_currency("SAN"), "USD")
        self.assertIsNone(default_currency("unknown airport"))

    def test_unspecified_currency_uses_origin(self):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(output_text=json.dumps({
            "intent": "itinerary", "total_budget": 1000, "currency": "USD",
            "currency_explicit": False, "origin": "TPE", "needs_clarification": False,
            "ambiguities": [], "clarification_question": None,
            "clarification_reason": "none", "new_trip": False, "state_changes": []}))
        result = classify_intent(client, [{"role": "user", "content": "從 TPE 出發，預算 1000"}])
        self.assertEqual(result["currency"], "TWD")

    def test_explicit_usd_is_preserved(self):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(output_text=json.dumps({
            "intent": "itinerary", "total_budget": 1000, "currency": "USD",
            "currency_explicit": True, "origin": "TPE", "needs_clarification": False,
            "ambiguities": [], "clarification_question": None,
            "clarification_reason": "none", "new_trip": False, "state_changes": []}))
        result = classify_intent(client, [{"role": "user", "content": "從 TPE 出發，預算 USD 1000"}])
        self.assertEqual(result["currency"], "USD")

    def test_hotel_search_uses_requested_currency(self):
        provider_result = Mock()
        provider_result.as_dict.return_value = {"properties": []}
        with patch("tools.hotels.client.search", return_value=provider_result) as search:
            result = search_hotels("Tokyo", "2026-11-06", "2026-11-09",
                                   max_price=3000, currency="TWD")
        self.assertEqual(search.call_args.args[0]["currency"], "TWD")
        self.assertEqual(search.call_args.args[0]["max_price"], 3000)
        self.assertEqual(result["currency"], "TWD")

    def test_hotel_search_exposes_full_multi_night_price(self):
        provider_result = Mock()
        provider_result.as_dict.return_value = {"properties": [{
            "name": "Example Hotel",
            "rate_per_night": {"extracted_lowest": 100},
            "total_rate": {"extracted_lowest": 300},
        }]}
        with patch("tools.hotels.client.search", return_value=provider_result) as search:
            result = search_hotels("Tokyo", "2026-11-06", "2026-11-09")
        params = search.call_args.args[0]
        self.assertEqual((params["check_in_date"], params["check_out_date"]),
                         ("2026-11-06", "2026-11-09"))
        self.assertEqual(result["stay_nights"], 3)
        self.assertEqual(result["properties"][0]["full_stay_price"], 300)

    def test_hotel_search_rejects_reversed_dates(self):
        with patch("tools.hotels.client.search") as search:
            with self.assertRaises(ValueError):
                search_hotels("Tokyo", "2026-11-09", "2026-11-06")
        search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
