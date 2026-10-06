import os
from datetime import date
import serpapi
from dotenv import load_dotenv

load_dotenv()

client = serpapi.Client(
    api_key=os.getenv("SERPAPI_API_KEY")
)

def search_hotels(
    location,
    check_in_date,
    check_out_date,
    adults=1,
    max_price=None,
    currency="USD",
):
    stay_nights = (date.fromisoformat(check_out_date) - date.fromisoformat(check_in_date)).days
    if stay_nights < 1:
        raise ValueError("check_out_date must be after check_in_date")
    currency = currency.upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("currency must be a three-letter code")
    params = {
        "engine": "google_hotels",
        "q": location,
        "check_in_date": check_in_date,
        "check_out_date": check_out_date,
        "adults": adults,
        "currency": currency,
    }

    if max_price is not None:
        params["max_price"] = max_price

    results = client.search(params)
    data = results.as_dict()
    data["currency"] = currency
    data["stay_nights"] = stay_nights
    for property_result in data.get("properties", []):
        if isinstance(property_result, dict):
            total_rate = property_result.get("total_rate")
            if isinstance(total_rate, dict) and total_rate.get("extracted_lowest") is not None:
                property_result["full_stay_price"] = total_rate["extracted_lowest"]
    return data
