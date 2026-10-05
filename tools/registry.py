from tools.flights import search_flights
from tools.hotels import search_hotels
from tools.places import search_places
from utils.budget import check_budget

TOOLS = [{
    "type": "function",
    "name": "search_flights",
    "description": "Search Google Flights for one-way or round-trip flight options and prices in USD.",
    "strict": False,
    "parameters": {
        "type": "object",
        "properties": {
            "origin": {"type": "string", "description": "Departure airport IATA code, e.g. TPE."},
            "destination": {"type": "string", "description": "Arrival airport IATA code, e.g. SEA."},
            "departure_date": {"type": "string", "description": "Departure date in YYYY-MM-DD format."},
            "return_date": {"type": ["string", "null"], "description": "Return date in YYYY-MM-DD format, or null for one-way."},
            "max_price": {"type": ["number", "null"], "description": "Maximum flight price in USD, or null for no limit."},
            "nonstop": {"type": ["boolean", "null"], "description": "Whether to only show nonstop flights, or null for no preference."},
            "sorted_by": {"type": ["string", "null"],"enum": ["price", "duration", None], "description": "How to sort the results, or null for no sorting."},
        },
        "required": ["origin", "destination", "departure_date", "return_date"],
        "additionalProperties": False,
    },
},
{
    "type": "function",
    "name": "search_hotels",
    "description": "Search Google Hotels for hotel options and prices in USD.",
    "strict": False,
    "parameters": {
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "City or area to search for hotels."},
            "check_in_date": {"type": "string", "description": "Check-in date in YYYY-MM-DD format."},
            "check_out_date": {"type": "string", "description": "Check-out date in YYYY-MM-DD format."},
            "adults": {"type": "integer", "description": "Number of adults staying in the hotel."},
            "max_price": {"type": ["number", "null"], "description": "Maximum hotel price per night in USD, or null for no limit."},
        },
        "required": ["location", "check_in_date", "check_out_date", "adults"],
        "additionalProperties": False,
    },
},
{
    "type": "function",
    "name": "search_places",
    "description": "Search Google Maps for places, attractions, and points of interest.",
    "strict": False,
    "parameters": {
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "City or area to search for places."},
            "query": {"type": "string", "description": "Search query for the type of place or attraction."},
        },
        "required": ["location", "query"],
        "additionalProperties": False,
    },
}
]


TOOLS.append({
    "type": "function",
    "name": "check_budget",
    "description": "Check a complete itinerary against a user-supplied total trip budget, or perform an explicitly requested budget compliance check. Do not use for simple searches or when no spending limit is supplied. All amounts must use the same currency and cover the same travelers and trip duration.",
    "strict": False,
    "parameters": {
        "type": "object",
        "properties": {
            "total_budget": {"type": "number", "description": "Total budget for the whole trip."},
            "costs": {
                "type": "object",
                "description": "Total expenses by category, such as flights, accommodation, meals, transportation, activities, and miscellaneous.",
                "additionalProperties": {"type": "number"},
            },
        },
        "required": ["total_budget", "costs"],
        "additionalProperties": False,
    },
})

TOOL_FUNCTIONS = {
    "search_flights": search_flights,
    "search_hotels": search_hotels,
    "search_places": search_places,
    "check_budget": check_budget,
}


def execute_tool(name, arguments):
    if name not in TOOL_FUNCTIONS:
        raise ValueError(f"Unknown tool: {name}")
    return TOOL_FUNCTIONS[name](**arguments)
