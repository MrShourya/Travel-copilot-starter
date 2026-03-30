import re

from app.mcp.currency_client import CurrencyMCPClient
from app.mcp.weather_client import WeatherMCPClient

weather_client = WeatherMCPClient()
currency_client = CurrencyMCPClient()

from datetime import date, timedelta


async def maybe_get_weather(user_query: str) -> dict | None:
    keywords = [
        "weather",
        "rain",
        "forecast",
        "temperature",
        "hot",
        "cold",
        "next week",
        "tomorrow",
        "this weekend",
        "weekend",
    ]
    if not any(word in user_query.lower() for word in keywords):
        return None

    city = extract_city(user_query)
    days = extract_trip_days(user_query)
    query_lower = user_query.lower()

    if "next week" in query_lower or "forecast" in query_lower or "tomorrow" in query_lower:
        start_date = date.today() + timedelta(days=7) if "next week" in query_lower else date.today()
        end_date = start_date + timedelta(days=max(days - 1, 0))

        result = await weather_client.call_tool(
            tool_name="get_weather_byDateTimeRange",
            arguments={
                "city": city,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        )
        return result.content

    result = await weather_client.call_tool(
        tool_name="get_current_weather",
        arguments={"city": city},
    )
    return result.content

async def maybe_convert_currency(user_query: str) -> dict | None:
    keywords = ["aed", "usd", "eur", "inr", "convert", "budget", "currency", "under"]
    if not any(word in user_query.lower() for word in keywords):
        return None

    amount, detected_currency = extract_amount_and_currency(user_query)
    target_currency = extract_target_currency(user_query)

    # No explicit target currency -> do not convert
    if not target_currency:
        return {
            "amount": amount,
            "from_currency": detected_currency,
            "to_currency": None,
            "converted_amount": None,
            "note": "No target currency specified, so no conversion was performed.",
        }

    if detected_currency == target_currency:
        return {
            "amount": amount,
            "from_currency": detected_currency,
            "to_currency": target_currency,
            "converted_amount": amount,
            "rate": 1.0,
            "note": "No conversion needed because source and target currencies are the same.",
        }

    # Direct lookup
    result = await currency_client.call_tool(
        tool_name="get_latest_rates",
        arguments={
            "base": detected_currency,
            "symbols": target_currency,
        },
    )

    content = result.content
    if "rates" in content and target_currency in content["rates"]:
        rate = content["rates"][target_currency]
        return {
            "amount": amount,
            "from_currency": detected_currency,
            "to_currency": target_currency,
            "date": content.get("date"),
            "rate": rate,
            "converted_amount": round(amount * rate, 2),
            "source": "Remote Currency MCP (direct latest rates)",
        }

    # USD bridge fallback
    bridge_result = await currency_client.call_tool(
        tool_name="get_latest_rates",
        arguments={
            "base": "USD",
            "symbols": f"{detected_currency},{target_currency}",
        },
    )

    bridge_content = bridge_result.content
    rates = bridge_content.get("rates", {})

    if detected_currency in rates and target_currency in rates:
        source_rate = rates[detected_currency]
        target_rate = rates[target_currency]
        cross_rate = target_rate / source_rate

        return {
            "amount": amount,
            "from_currency": detected_currency,
            "to_currency": target_currency,
            "date": bridge_content.get("date"),
            "rate": cross_rate,
            "converted_amount": round(amount * cross_rate, 2),
            "source": "Remote Currency MCP (USD bridge rate)",
            "bridge_base": "USD",
        }

    return {
        "amount": amount,
        "from_currency": detected_currency,
        "to_currency": target_currency,
        "converted_amount": None,
        "note": (
            f"Remote currency MCP could not provide a usable rate for "
            f"{detected_currency}->{target_currency}."
        ),
        "raw_response": {
            "direct": content,
            "bridge": bridge_content,
        },
    }

def extract_target_currency(user_query: str) -> str | None:
    query_lower = user_query.lower()

    patterns = [
        r"\bto\s+(usd|eur|inr)\b",
        r"\bin\s+(usd|eur|inr)\b",
        r"\bshow\s+budget\s+in\s+(usd|eur|inr)\b",
        r"\bconvert\s+to\s+(usd|eur|inr)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, query_lower)
        if match:
            return match.group(1).upper()

    return None

def extract_city(user_query: str) -> str:
    known_cities = [
        "tokyo",
        "paris",
        "dubai",
        "muscat",
        "singapore",
        "istanbul",
        "rome",
        "vienna",
        "zurich",
        "abu dhabi",
        "delhi",
        "bangkok",
        "mumbai",
    ]
    query_lower = user_query.lower()
    for city in known_cities:
        if city in query_lower:
            return city.title()
    return "Unknown"


def extract_trip_days(user_query: str) -> int:
    match = re.search(r"(\d+)[-\s]?day", user_query.lower())
    if match:
        return int(match.group(1))
    return 3


def extract_amount_and_currency(user_query: str) -> tuple[float, str]:
    query_lower = user_query.lower()

    match = re.search(r"(\d+(?:\.\d+)?)\s*(usd|eur|inr)", query_lower)
    if match:
        amount = float(match.group(1))
        currency = match.group(2).upper()
        return amount, currency

    match = re.search(r"under\s*(\d+(?:\.\d+)?)\s*(usd|eur|inr)?", query_lower)
    if match:
        amount = float(match.group(1))
        currency = (match.group(2) or "USD").upper()
        return amount, currency

    return 1000.0, "USD"