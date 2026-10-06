"""Trim search-provider metadata before sending results back to the model."""

SEARCH_FIELDS = {
    "error", "flights", "price", "type", "total_duration", "layovers", "adults",
    "round_trip_options", "outbound", "return_options", "return_search_status",
    "return_search_error", "independent_return_options",
    "duration", "airline", "flight_number", "departure_airport",
    "arrival_airport", "time", "name", "id", "travel_class", "stops",
    "price_insights", "lowest_price", "price_level", "typical_price_range",
    "properties", "rate_per_night", "total_rate", "stay_nights", "full_stay_price", "lowest",
    "extracted_lowest", "before_taxes_fees", "extracted_before_taxes_fees",
    "hotel_class", "extracted_hotel_class", "overall_rating", "rating",
    "reviews", "address", "description", "amenities", "gps_coordinates",
    "latitude", "longitude", "local_results", "place_results", "title",
    "place_id", "types", "hours", "operating_hours", "open_state",
    "check_in_time", "check_out_time", "currency", "website", "phone",
}


def compact_tool_result(value, tool_name):
    if tool_name not in {"search_flights", "search_hotels", "search_places"}:
        return value

    def keep(item):
        if isinstance(item, dict):
            return {key: keep(child) for key, child in item.items()
                    if key in SEARCH_FIELDS}
        if isinstance(item, list):
            return [keep(child) for child in item]
        return item

    return keep(value)
