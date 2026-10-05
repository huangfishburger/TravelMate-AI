import os
import serpapi
from dotenv import load_dotenv

load_dotenv()

client = serpapi.Client(
    api_key=os.getenv("SERPAPI_API_KEY")
)

def search_places(
    location,
    query,
):
    params = {
        "engine": "google_maps",
        "q": f"{query} in {location}",
        "type": "search",
        "hl": "en"
    }

    results = client.search(params)

    return results.as_dict()
