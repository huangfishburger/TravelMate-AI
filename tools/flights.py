import os
import serpapi
from dotenv import load_dotenv

load_dotenv()

client = serpapi.Client(
    api_key=os.getenv("SERPAPI_API_KEY")
)

def search_flights(
    origin, 
    destination, 
    departure_date, 
    return_date=None, 
    max_price=None,
    nonstop=False,
    sorted_by=None,
    currency="USD",
    adults=1,
):
    currency = currency.upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("currency must be a three-letter code")
    if isinstance(adults, bool) or not isinstance(adults, int) or adults < 1:
        raise ValueError("adults must be a positive integer")
    params = {
        "engine": "google_flights",
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": departure_date,
        "currency": currency,
        "adults": adults,
        "hl": "en"
    }

    if return_date:
        params["type"] = 1  # round-trip
        params["return_date"] = return_date
    else:
        params["type"] = 2  # one-way

    if max_price:
        params["max_price"] = max_price

    if nonstop:
        params["stops"] = 1

    if sorted_by == "price":
        params["sort_by"] = 2
    elif sorted_by == "duration":
        params["sort_by"] = 5

    results = client.search(params)
    processed = process_flight_results(results)
    processed["currency"] = currency
    processed["adults"] = adults
    if not return_date or "error" in processed:
        return processed

    # SerpApi first returns outbound choices. A departure_token selects one of
    # them and retrieves the return choices priced with that outbound flight.
    round_trip_options = []
    errors = []
    for outbound in processed["flights"][:5]:
        token = outbound.get("departure_token")
        if not token:
            continue
        try:
            return_results = client.search({**params, "departure_token": token})
            returns = process_flight_results(return_results)
            if "error" in returns:
                errors.append(returns["error"])
                continue
            round_trip_options.append({
                "outbound": {key: value for key, value in outbound.items()
                             if key != "departure_token"},
                "return_options": returns["flights"][:5],
            })
        except Exception as exc:
            errors.append(str(exc))
    processed["round_trip_options"] = round_trip_options
    if not round_trip_options:
        processed["return_search_status"] = (
            "Paired return options unavailable. Independent one-way return prices "
            "are not the original outbound listing's round-trip fare."
        )
        if errors:
            processed["return_search_error"] = errors[0]
        try:
            fallback_params = {**params, "departure_id": destination,
                               "arrival_id": origin, "outbound_date": return_date,
                               "type": 2}
            fallback_params.pop("return_date", None)
            fallback = process_flight_results(client.search(fallback_params))
            if "error" in fallback:
                processed["return_search_error"] = fallback["error"]
            else:
                processed["independent_return_options"] = fallback["flights"][:5]
        except Exception as exc:
            processed["return_search_error"] = str(exc)
    return processed


def process_flight_results(results):
    """Process flight search results to extract relevant information."""

    if results.get("error"):
        return {"error": results["error"]}

    flights = (
        results.get("best_flights", [])
        + results.get("other_flights", [])
    )

    price_insights = results.get("price_insights", {})

    processed_price_insights = {
        "lowest_price": price_insights.get("lowest_price"),
        "price_level": price_insights.get("price_level"),
        "typical_price_range": price_insights.get("typical_price_range")
    }

    return {
        "flights": flights[:15],
        "price_insights": processed_price_insights,
    }
