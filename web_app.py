"""Local travel-planner web UI. Run with: python web_app.py"""

from copy import deepcopy
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Lock
from uuid import uuid4

from agent import preferred_response_language, run_agent
from memory import new_memory
from multimodal import image_part
from token_usage import token_totals


ROOT = Path(__file__).resolve().parent
SESSIONS = {}
SESSIONS_LOCK = Lock()
STATIC = {"/": ("web/index.html", "text/html; charset=utf-8"),
          "/editor": ("web/editor.html", "text/html; charset=utf-8"),
          "/editor.js": ("web/editor.js", "text/javascript; charset=utf-8"),
          "/editor.css": ("web/editor.css", "text/css; charset=utf-8"),
          "/app.css": ("web/app.css", "text/css; charset=utf-8"),
          "/app.js": ("web/app.js", "text/javascript; charset=utf-8")}
MAX_IMAGES = 3
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def request_images(payload):
    images = payload.get("images", [])
    if not isinstance(images, list) or len(images) > MAX_IMAGES:
        raise ValueError("Attach at most three images")
    sources, names = [], []
    for item in images:
        if not isinstance(item, dict) or not isinstance(item.get("data_url"), str):
            raise ValueError("Invalid image attachment")
        source = item["data_url"]
        if len(source) > MAX_IMAGE_BYTES * 4 // 3 + 128:
            raise ValueError("Each image must be at most 8 MB")
        image_part(source)
        sources.append(source)
        names.append(str(item.get("name") or "Image")[:100])
    return sources, names


def activity_from_trace(trace):
    activity = []
    names = {"search_flights": "Searched flights", "search_hotels": "Searched hotels",
             "search_places": "Searched places", "check_budget": "Budget checked"}
    for event in trace:
        kind = event.get("event")
        if kind == "tool_call" and event.get("name") in names:
            result = event.get("result") or {}
            if "error" in result:
                error_type = result.get("error_type", "")
                if error_type in {"HTTPConnectionError", "ConnectionError", "ProxyError", "Timeout"}:
                    reason = "connection failed"
                elif result.get("status_code") in {401, 403}:
                    reason = "API access denied"
                elif result.get("status_code") == 429:
                    reason = "API rate limit"
                else:
                    reason = "provider error"
                activity.append({"status": "warning", "label": names[event["name"]] + " · " + reason})
            else:
                activity.append({"status": "done", "label": names[event["name"]]})
                if event["name"] == "search_flights" and not result.get("flights"):
                    activity.append({"status": "warning", "label": "No flight options returned for this search"})
                if event["name"] == "check_budget" and result.get("within_budget") is False:
                    activity.append({"status": "warning", "label": "Plan exceeded budget"})
                elif event["name"] == "check_budget" and result.get("within_budget") is True:
                    activity.append({"status": "done", "label":
                                     f"Checked total: {result.get('total_cost')} / {result.get('budget')}"})
        elif kind == "budget_replan":
            activity.append({"status": "progress", "label": "Replanned to reduce cost"})
        elif kind == "quality_replan":
            activity.append({"status": "progress", "label": "Revised itinerary after quality review"})
        elif kind == "clarification":
            activity.append({"status": "warning", "label": "Asked for clarification"})
    return activity


def progress_from_trace(trace):
    labels = {"intent_start": "Understanding your request",
              "planner_start": "Planning your itinerary",
              "planner_model_start": "Putting the itinerary together",
              "evaluation_start": "Reviewing itinerary quality",
              "selection_start": "Saving flight and hotel choices",
              "budget_replan": "Replanning to fit your budget",
              "quality_replan": "Improving the itinerary after review"}
    tool_labels = {"search_flights": "Searching flights",
                   "search_hotels": "Searching hotels",
                   "search_places": "Finding places to visit",
                   "check_budget": "Checking the total budget"}
    for event in reversed(trace):
        kind = event.get("event")
        if kind == "tool_start":
            return tool_labels.get(event.get("name"), "Checking trip details")
        if kind in labels:
            return labels[kind]
    return "Starting your trip plan"


def flight_searches_from_trace(trace):
    def option(item):
        legs = item.get("flights") or []
        first = legs[0] if legs else {}
        last = legs[-1] if legs else {}
        departure = first.get("departure_airport") or {}
        arrival = last.get("arrival_airport") or {}
        return {"price": item.get("price"),
                "departure": departure.get("time"), "arrival": arrival.get("time"),
                "route": f"{departure.get('id', '?')} → {arrival.get('id', '?')}",
                "airline": first.get("airline"), "flight_number": first.get("flight_number"),
                "stops": len(legs) - 1 if legs else None}

    searches = []
    for event in trace:
        if event.get("event") != "tool_call" or event.get("name") != "search_flights":
            continue
        args = event.get("args") or {}
        result = event.get("result") or {}
        searches.append({
            "query": {key: args.get(key) for key in ("origin", "destination", "departure_date",
                                                "return_date", "currency", "adults", "max_price", "nonstop", "sorted_by")},
            "error": result.get("error"),
            "outbound_options": [option(item) for item in result.get("flights", [])],
            "paired_options": [{"outbound": option(pair.get("outbound") or {}),
                                "returns": [option(item) for item in pair.get("return_options", [])]}
                               for pair in result.get("round_trip_options", [])],
            "return_search_status": result.get("return_search_status"),
            "independent_returns": [option(item) for item in result.get("independent_return_options", [])],
        })
    return searches


def public_answer(answer):
    if isinstance(answer, dict):
        return {key: answer.get(key) for key in
                ("response", "costs", "total_cost", "remaining", "total_budget",
                 "currency", "within_budget", "evaluation") if key in answer}
    return {"response": str(answer)}


class Handler(BaseHTTPRequestHandler):
    def session(self):
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        sid = cookie["trip_session"].value if "trip_session" in cookie else ""
        with SESSIONS_LOCK:
            if sid not in SESSIONS:
                sid = uuid4().hex
                SESSIONS[sid] = {"history": [], "memory": new_memory(),
                                 "messages": [], "lock": Lock(), "active_trace": None}
        return sid, SESSIONS[sid]

    def send_data(self, data, status=HTTPStatus.OK, content_type="application/json; charset=utf-8", sid=None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8") if not isinstance(data, bytes) else data
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if sid:
            self.send_header("Set-Cookie", f"trip_session={sid}; HttpOnly; SameSite=Lax; Path=/")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in STATIC:
            path, content_type = STATIC[self.path]
            self.send_data((ROOT / path).read_bytes(), content_type=content_type)
        elif self.path == "/api/progress":
            sid, session = self.session()
            trace = session.get("active_trace")
            snapshot = list(trace) if trace is not None else []
            self.send_data({"active": trace is not None,
                            "label": progress_from_trace(snapshot) if trace is not None else "",
                            "activity": activity_from_trace(snapshot)}, sid=sid)
        elif self.path == "/api/state":
            sid, session = self.session()
            with session["lock"]:
                data = {"memory": deepcopy(session["memory"]),
                        "messages": deepcopy(session["messages"])}
            self.send_data(data, sid=sid)
        else:
            self.send_data({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self):
        if self.path not in {"/api/chat", "/api/reset"}:
            return self.send_data({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        if int(self.headers.get("Content-Length", "0")) > 34 * 1024 * 1024:
            return self.send_data({"error": "Request too large"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        sid, session = self.session()
        if self.path == "/api/reset":
            with session["lock"]:
                session.update(history=[], memory=new_memory(), messages=[])
            return self.send_data({"memory": session["memory"], "messages": []}, sid=sid)
        try:
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            prompt = payload.get("prompt", "").strip()
            images, image_names = request_images(payload)
            if (not prompt and not images) or len(prompt) > 10000:
                raise ValueError("Enter a request or attach an image; text may be at most 10,000 characters")
            with session["lock"]:
                trace = []
                response_language = preferred_response_language(prompt, session["history"])
                session["active_trace"] = trace
                try:
                    answer = run_agent(prompt, history=session["history"], memory=session["memory"],
                                       trace=trace, images=images or None)
                finally:
                    session["active_trace"] = None
                result = public_answer(answer)
                selected = session["memory"]["trip_state"].get("selected", {})
                logistics = deepcopy(selected) if result.get("evaluation") is not None else None
                session["messages"].extend([{"role": "user", "content": prompt,
                                             "images": image_names},
                                            {"role": "assistant", **result,
                                            "logistics": logistics,
                                            "response_language": response_language,
                                            "activity": activity_from_trace(trace),
                                            "flight_searches": flight_searches_from_trace(trace),
                                            "token_usage": token_totals(trace)}])
                data = {"answer": result, "memory": deepcopy(session["memory"]),
                        "messages": deepcopy(session["messages"])}
            self.send_data(data, sid=sid)
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_data({"error": str(exc)}, HTTPStatus.BAD_REQUEST, sid=sid)
        except Exception as exc:
            self.send_data({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR, sid=sid)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    print("Travel planner UI: http://127.0.0.1:8000")
    server.serve_forever()
