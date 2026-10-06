"""Default an unspecified trip budget currency from a known departure point."""

ORIGIN_CURRENCIES = {
    "TPE": "TWD", "TSA": "TWD", "KHH": "TWD", "TAIWAN": "TWD", "TAIPEI": "TWD", "台灣": "TWD", "臺灣": "TWD", "台北": "TWD", "臺北": "TWD", "桃園": "TWD",
    "NRT": "JPY", "HND": "JPY", "KIX": "JPY", "FUK": "JPY", "JAPAN": "JPY", "TOKYO": "JPY", "日本": "JPY", "東京": "JPY",
    "SAN": "USD", "SEA": "USD", "LAX": "USD", "SFO": "USD", "JFK": "USD", "USA": "USD", "UNITED STATES": "USD", "美國": "USD",
    "HKG": "HKD", "HONG KONG": "HKD", "香港": "HKD",
    "SIN": "SGD", "SINGAPORE": "SGD", "新加坡": "SGD",
    "ICN": "KRW", "GMP": "KRW", "SOUTH KOREA": "KRW", "SEOUL": "KRW", "首爾": "KRW", "韓國": "KRW",
    "LHR": "GBP", "LGW": "GBP", "LONDON": "GBP", "UNITED KINGDOM": "GBP", "英國": "GBP",
    "CDG": "EUR", "ORY": "EUR", "FRA": "EUR", "AMS": "EUR", "PARIS": "EUR", "FRANCE": "EUR", "法國": "EUR",
}


def default_currency(origin):
    if not isinstance(origin, str):
        return None
    return ORIGIN_CURRENCIES.get(origin.strip().upper())
