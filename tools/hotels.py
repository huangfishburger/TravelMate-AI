import os
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
    max_price=None
):
    params = {
        "engine": "google_hotels",
        "q": location,
        "check_in_date": check_in_date,
        "check_out_date": check_out_date,
        "adults": adults,
        "currency": "USD",
    }

    if max_price is not None:
        params["max_price"] = max_price

    results = client.search(params)
    return results.as_dict()
