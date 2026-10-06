import unittest
from unittest.mock import patch

from tools.flights import search_flights


OUTBOUND = {"flights": [{"departure_airport": {"id": "SAN", "time": "2026-11-06 06:15"},
                         "arrival_airport": {"id": "SEA", "time": "2026-11-06 09:27"},
                         "flight_number": "AS 608"}],
            "price": 207, "departure_token": "outbound-token"}
RETURN = {"flights": [{"departure_airport": {"id": "SEA", "time": "2026-11-08 11:43"},
                       "arrival_airport": {"id": "SAN", "time": "2026-11-08 14:47"},
                       "flight_number": "AS 650"}], "price": 229}


class FlightTests(unittest.TestCase):
    def test_round_trip_token_returns_paired_options(self):
        queries = []
        def search(params):
            queries.append(params)
            return {"best_flights": [RETURN]} if params.get("departure_token") else {"best_flights": [OUTBOUND]}
        with patch("tools.flights.client.search", side_effect=search):
            result = search_flights("SAN", "SEA", "2026-11-06", "2026-11-08")
        self.assertEqual(len(queries), 2)
        self.assertEqual(queries[1]["departure_token"], "outbound-token")
        pair = result["round_trip_options"][0]
        self.assertEqual(pair["return_options"][0]["flights"][0]["flight_number"], "AS 650")
        self.assertEqual(pair["return_options"][0]["price"], 229)
        self.assertNotIn("departure_token", pair["outbound"])

    def test_missing_pair_uses_labeled_one_way_fallback(self):
        queries = []
        def search(params):
            queries.append(params)
            return {"best_flights": [RETURN]} if params["departure_id"] == "SEA" else {"best_flights": [{
                "flights": OUTBOUND["flights"], "price": 207}]}
        with patch("tools.flights.client.search", side_effect=search):
            result = search_flights("SAN", "SEA", "2026-11-06", "2026-11-08")
        self.assertEqual(queries[-1]["departure_id"], "SEA")
        self.assertEqual(queries[-1]["type"], 2)
        self.assertNotIn("return_date", queries[-1])
        self.assertEqual(result["independent_return_options"][0]["price"], 229)
        self.assertIn("not the original", result["return_search_status"])

    def test_one_way_does_not_fetch_return(self):
        with patch("tools.flights.client.search", return_value={"best_flights": [OUTBOUND]}) as search:
            result = search_flights("SAN", "SEA", "2026-11-06")
        self.assertEqual(search.call_count, 1)
        self.assertNotIn("round_trip_options", result)

    def test_requested_currency_applies_to_flight_search_and_price_cap(self):
        with patch("tools.flights.client.search", return_value={"best_flights": [OUTBOUND]}) as search:
            result = search_flights("TPE", "HND", "2026-11-06", max_price=10000, currency="TWD")
        self.assertEqual(search.call_args.args[0]["currency"], "TWD")
        self.assertEqual(search.call_args.args[0]["max_price"], 10000)
        self.assertEqual(result["currency"], "TWD")

    def test_multiple_tokyo_airports_use_one_search(self):
        with patch("tools.flights.client.search", return_value={"best_flights": [OUTBOUND]}) as search:
            search_flights("TPE", "HND,NRT", "2026-11-06", currency="TWD")
        self.assertEqual(search.call_count, 1)
        self.assertEqual(search.call_args.args[0]["arrival_id"], "HND,NRT")

    def test_passenger_count_reaches_provider_and_result(self):
        with patch("tools.flights.client.search", return_value={"best_flights": [OUTBOUND]}) as search:
            result = search_flights("TPE", "HND", "2026-11-06", adults=2, currency="TWD")
        self.assertEqual(search.call_args.args[0]["adults"], 2)
        self.assertEqual(result["adults"], 2)


if __name__ == "__main__":
    unittest.main()
