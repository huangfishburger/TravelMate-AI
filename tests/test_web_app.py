import http.client
import base64
from http.server import ThreadingHTTPServer
import json
from threading import Event, Thread
import unittest
from unittest.mock import patch

from web_app import Handler, activity_from_trace, flight_searches_from_trace, progress_from_trace
from utils.multimodal import image_part


class WebAppTests(unittest.TestCase):
    def test_flight_search_audit_keeps_filters_and_options_without_tokens(self):
        flight = {"price": 8500, "departure_token": "secret-provider-token", "flights": [{
            "airline": "Example Air", "flight_number": "EX 123",
            "departure_airport": {"id": "TPE", "time": "2026-11-06 10:00"},
            "arrival_airport": {"id": "HND", "time": "2026-11-06 14:00"}}]}
        audit = flight_searches_from_trace([{"event": "tool_call", "name": "search_flights",
            "args": {"origin": "TPE", "destination": "HND", "departure_date": "2026-11-06",
                     "currency": "TWD", "sorted_by": "price"},
            "result": {"flights": [flight], "round_trip_options": [{
                "outbound": flight, "return_options": [flight]}]}}])
        self.assertEqual(audit[0]["query"]["sorted_by"], "price")
        self.assertEqual(audit[0]["outbound_options"][0]["departure"], "2026-11-06 10:00")
        self.assertEqual(audit[0]["paired_options"][0]["returns"][0]["price"], 8500)
        self.assertNotIn("secret-provider-token", json.dumps(audit))

    def test_progress_uses_latest_running_stage(self):
        self.assertEqual(progress_from_trace([
            {"event": "intent_start"}, {"event": "planner_start"},
            {"event": "tool_start", "name": "search_flights"}]), "Searching flights")
        self.assertEqual(progress_from_trace([
            {"event": "tool_start", "name": "check_budget"},
            {"event": "evaluation_start"}]), "Reviewing itinerary quality")

    def test_progress_endpoint_reports_active_tool(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        started, release = Event(), Event()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
        poll = http.client.HTTPConnection("127.0.0.1", server.server_port)

        def fake_agent(prompt, history, memory, trace, images=None):
            trace.extend([{"event": "tool_call", "name": "search_flights",
                           "result": {"flights": [{"price": 100}]}},
                          {"event": "tool_start", "name": "search_hotels"}])
            started.set()
            release.wait(3)
            return "Plan ready"

        def send_chat():
            connection.request("POST", "/api/chat", json.dumps({"prompt": "Plan a trip"}),
                               {"Content-Type": "application/json", "Cookie": cookie})
            connection.getresponse().read()

        try:
            poll.request("GET", "/api/state")
            initial = poll.getresponse()
            cookie = initial.getheader("Set-Cookie").split(";", 1)[0]
            initial.read()
            with patch("web_app.run_agent", side_effect=fake_agent):
                worker = Thread(target=send_chat, daemon=True)
                worker.start()
                self.assertTrue(started.wait(2))
                poll.request("GET", "/api/progress", headers={"Cookie": cookie})
                response = poll.getresponse()
                data = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertTrue(data["active"])
                self.assertEqual(data["label"], "Searching hotels")
                self.assertEqual(data["activity"][0]["label"], "Searched flights")
                release.set()
                worker.join(3)
        finally:
            release.set()
            connection.close()
            poll.close()
            server.shutdown()
            server.server_close()

    def test_editor_assets_are_served(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
        try:
            for path, content_type in (("/editor", "text/html"),
                                       ("/editor.js", "text/javascript"),
                                       ("/editor.css", "text/css")):
                connection.request("GET", path)
                response = connection.getresponse()
                body = response.read()
                self.assertEqual(response.status, 200, path)
                self.assertIn(content_type, response.getheader("Content-Type"))
                self.assertTrue(body, path)
        finally:
            connection.close()
            server.shutdown()
            server.server_close()

    def test_activity_is_user_facing(self):
        activity = activity_from_trace([
            {"event": "tool_call", "name": "search_flights", "result": {"flights": [{"price": 100}]}},
            {"event": "tool_call", "name": "check_budget", "result": {
                "within_budget": False, "budget": 1000, "total_cost": 1100}},
            {"event": "budget_replan"},
        ])
        self.assertEqual([item["label"] for item in activity],
                         ["Searched flights", "Budget checked", "Plan exceeded budget",
                          "Replanned to reduce cost"])

    def test_activity_distinguishes_connection_failure_from_empty_results(self):
        failed = activity_from_trace([{"event": "tool_call", "name": "search_flights",
                                       "result": {"error": "search_flights failed", "error_type": "HTTPConnectionError"}}])
        self.assertEqual(failed[0]["label"], "Searched flights · connection failed")
        empty = activity_from_trace([{"event": "tool_call", "name": "search_flights",
                                      "result": {"flights": [], "currency": "TWD"}}])
        self.assertEqual(empty[-1]["label"], "No flight options returned for this search")

    def test_chat_state_and_reset(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port)

        def fake_agent(prompt, history, memory, trace, images=None):
            memory["trip_state"]["destination"] = "Seattle"
            memory["trip_state"]["selected"]["flight"] = {
                "outbound": {"date": "2026-11-06", "flight_number": "AS123",
                             "departure_time": "09:00", "arrival_time": "12:00"}}
            memory["trip_state"]["selected"]["hotel"] = {"stays": [{
                "name": "Test Hotel", "check_in_date": "2026-11-06",
                "check_out_date": "2026-11-08"}]}
            trace.append({"event": "intent", "usage": {
                "input_tokens": 10, "output_tokens": 2, "total_tokens": 12}})
            trace.append({"event": "tool_call", "name": "search_flights",
                          "args": {"origin": "SAN", "destination": "SEA",
                                   "departure_date": "2026-11-06", "currency": "USD"},
                          "result": {"flights": [{"price": 100}]}})
            return {"response": "Day 1: Coffee", "costs": {"food": 20},
                    "total_cost": 20, "total_budget": 1000, "currency": "USD",
                    "evaluation": {"overall_score": 8}}

        try:
            with patch("web_app.run_agent", side_effect=fake_agent):
                connection.request("POST", "/api/chat", json.dumps({"prompt": "Plan Seattle"}),
                                   {"Content-Type": "application/json"})
                response = connection.getresponse()
                cookie = response.getheader("Set-Cookie").split(";", 1)[0]
                data = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertEqual(data["memory"]["trip_state"]["destination"], "Seattle")
                self.assertEqual(data["messages"][-1]["token_usage"]["total_tokens"], 12)
                self.assertEqual(data["messages"][-1]["response_language"], "English")
                self.assertEqual(data["messages"][-1]["flight_searches"][0]["query"]["origin"], "SAN")
                self.assertEqual(data["messages"][-1]["logistics"]["hotel"]["stays"][0]["name"],
                                 "Test Hotel")
                connection.request("GET", "/api/state", headers={"Cookie": cookie})
                self.assertEqual(len(json.loads(connection.getresponse().read())["messages"]), 2)
                connection.request("POST", "/api/reset", "{}", {"Cookie": cookie})
                self.assertEqual(json.loads(connection.getresponse().read())["messages"], [])
        finally:
            connection.close()
            server.shutdown()
            server.server_close()

    def test_image_only_request_reaches_agent(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
        png = b"\x89PNG\r\n\x1a\n" + b"demo"
        data_url = "data:image/png;base64," + base64.b64encode(png).decode()
        try:
            with patch("web_app.run_agent", return_value="Looks like Seattle") as runner:
                connection.request("POST", "/api/chat", json.dumps({"prompt": "", "images": [
                    {"name": "place.png", "data_url": data_url}]}),
                    {"Content-Type": "application/json"})
                response = connection.getresponse()
                result = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertEqual(runner.call_args.kwargs["images"], [data_url])
                self.assertEqual(result["messages"][0]["images"], ["place.png"])
                self.assertNotIn("data:image", json.dumps(result))
        finally:
            connection.close()
            server.shutdown()
            server.server_close()

    def test_data_url_validates_mime(self):
        png = b"\x89PNG\r\n\x1a\n" + b"demo"
        encoded = base64.b64encode(png).decode()
        self.assertEqual(image_part("data:image/png;base64," + encoded)["type"], "input_image")
        with self.assertRaises(ValueError):
            image_part("data:image/jpeg;base64," + encoded)


if __name__ == "__main__":
    unittest.main()
