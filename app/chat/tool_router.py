import re
from datetime import date, timedelta
from typing import Any

from app.mcp.currency_client import CurrencyMCPClient
from app.mcp.travel_planning_client import TravelPlanningMCPClient
from app.mcp.weather_client import WeatherMCPClient

weather_client = WeatherMCPClient()
currency_client = CurrencyMCPClient()
travel_planning_client = TravelPlanningMCPClient()


def _wrap_result(
    *,
    mcp_family: str,
    tool_name: str | None,
    reason: str,
    arguments: dict[str, Any] | None,
    content: dict | None,
    skipped: bool = False,
) -> dict[str, Any]:
    return {
        "_decision": {
            "mcp_family": mcp_family,
            "tool_name": tool_name,
            "reason": reason,
            "arguments": arguments,
            "skipped": skipped,
        },
        "data": content,
    }


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

        arguments = {
            "city": city,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }

        result = await weather_client.call_tool(
            tool_name="get_weather_byDateTimeRange",
            arguments=arguments,
        )
        return _wrap_result(
            mcp_family="weather_mcp",
            tool_name="get_weather_byDateTimeRange",
            reason="Query mentions forecast/tomorrow/next week, so ranged weather was selected.",
            arguments=arguments,
            content=result.content,
        )

    arguments = {"city": city}
    result = await weather_client.call_tool(
        tool_name="get_current_weather",
        arguments=arguments,
    )
    return _wrap_result(
        mcp_family="weather_mcp",
        tool_name="get_current_weather",
        reason="Query asks about weather but not a future range, so current weather was selected.",
        arguments=arguments,
        content=result.content,
    )


async def maybe_convert_currency(user_query: str) -> dict | None:
    keywords = ["aed", "usd", "eur", "inr", "convert", "budget", "currency", "under"]
    if not any(word in user_query.lower() for word in keywords):
        return None

    amount, detected_currency = extract_amount_and_currency(user_query)
    target_currency = extract_target_currency(user_query)

    if not target_currency:
        return _wrap_result(
            mcp_family="currency_mcp",
            tool_name=None,
            reason="Currency-like query detected, but no explicit target currency was found, so MCP call was skipped.",
            arguments=None,
            content={
                "amount": amount,
                "from_currency": detected_currency,
                "to_currency": None,
                "converted_amount": None,
                "note": "No target currency specified, so no conversion was performed.",
            },
            skipped=True,
        )

    if detected_currency == target_currency:
        return _wrap_result(
            mcp_family="currency_mcp",
            tool_name=None,
            reason="Source and target currencies are the same, so MCP call was skipped.",
            arguments=None,
            content={
                "amount": amount,
                "from_currency": detected_currency,
                "to_currency": target_currency,
                "converted_amount": amount,
                "rate": 1.0,
                "note": "No conversion needed because source and target currencies are the same.",
            },
            skipped=True,
        )

    direct_arguments = {
        "base": detected_currency,
        "symbols": target_currency,
    }

    result = await currency_client.call_tool(
        tool_name="get_latest_rates",
        arguments=direct_arguments,
    )

    content = result.content
    if "rates" in content and target_currency in content["rates"]:
        rate = content["rates"][target_currency]
        return _wrap_result(
            mcp_family="currency_mcp",
            tool_name="get_latest_rates",
            reason="Direct latest-rates lookup succeeded.",
            arguments=direct_arguments,
            content={
                "amount": amount,
                "from_currency": detected_currency,
                "to_currency": target_currency,
                "date": content.get("date"),
                "rate": rate,
                "converted_amount": round(amount * rate, 2),
                "source": "Remote Currency MCP (direct latest rates)",
            },
        )

    bridge_arguments = {
        "base": "USD",
        "symbols": f"{detected_currency},{target_currency}",
    }

    bridge_result = await currency_client.call_tool(
        tool_name="get_latest_rates",
        arguments=bridge_arguments,
    )

    bridge_content = bridge_result.content
    rates = bridge_content.get("rates", {})

    if detected_currency in rates and target_currency in rates:
        source_rate = rates[detected_currency]
        target_rate = rates[target_currency]
        cross_rate = target_rate / source_rate

        return _wrap_result(
            mcp_family="currency_mcp",
            tool_name="get_latest_rates",
            reason="Direct lookup was insufficient, so USD bridge fallback was used.",
            arguments=bridge_arguments,
            content={
                "amount": amount,
                "from_currency": detected_currency,
                "to_currency": target_currency,
                "date": bridge_content.get("date"),
                "rate": cross_rate,
                "converted_amount": round(amount * cross_rate, 2),
                "source": "Remote Currency MCP (USD bridge rate)",
                "bridge_base": "USD",
            },
        )

    return _wrap_result(
        mcp_family="currency_mcp",
        tool_name="get_latest_rates",
        reason="Currency MCP was called, but neither direct nor USD bridge lookup produced a usable rate.",
        arguments={
            "direct": direct_arguments,
            "bridge": bridge_arguments,
        },
        content={
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
        },
    )


async def get_trip_readiness_from_mcp(state) -> dict | None:
    arguments = {
        "city": state.city,
        "trip_days": state.trip_days,
        "date_text": state.date_text,
        "budget_amount": state.budget_amount,
    }
    result = await travel_planning_client.call_tool(
        tool_name="trip_readiness_check_tool",
        arguments=arguments,
    )
    payload = result.content
    return _wrap_result(
        mcp_family="travel_planning_mcp",
        tool_name="trip_readiness_check_tool",
        reason="State reached show_itinerary, so readiness check was called first.",
        arguments=arguments,
        content=payload,
    )


async def get_trip_summary_from_mcp(state) -> dict | None:
    arguments = {
        "city": state.city,
        "trip_days": state.trip_days,
        "date_text": state.date_text,
        "budget_amount": state.budget_amount,
        "budget_currency": state.budget_currency,
        "target_currency": state.target_currency,
        "travel_style": "midrange",
    }
    result = await travel_planning_client.call_tool(
        tool_name="build_trip_summary_tool",
        arguments=arguments,
    )
    payload = result.content
    return _wrap_result(
        mcp_family="travel_planning_mcp",
        tool_name="build_trip_summary_tool",
        reason="Trip is ready enough for summary generation, so summary tool was called.",
        arguments=arguments,
        content=payload,
    )


async def get_budget_from_travel_mcp(state) -> dict | None:
    if not state.city or not state.trip_days:
        return _wrap_result(
            mcp_family="travel_planning_mcp",
            tool_name=None,
            reason="Budget estimation was skipped because city or trip_days is missing.",
            arguments=None,
            content=None,
            skipped=True,
        )

    currency = state.target_currency or state.budget_currency or "USD"
    arguments = {
        "city": state.city,
        "trip_days": state.trip_days,
        "travel_style": "midrange",
        "currency": currency,
    }

    result = await travel_planning_client.call_tool(
        tool_name="estimate_daily_budget_tool",
        arguments=arguments,
    )
    payload = result.content
    return _wrap_result(
        mcp_family="travel_planning_mcp",
        tool_name="estimate_daily_budget_tool",
        reason="Trip has enough structure for budget estimation, so budget MCP was called.",
        arguments=arguments,
        content=payload,
    )


def extract_target_currency(user_query: str) -> str | None:
    query_lower = user_query.lower()

    patterns = [
        r"\bto\s+(usd|eur|inr|aed)\b",
        r"\bin\s+(usd|eur|inr|aed)\b",
        r"\bshow\s+budget\s+in\s+(usd|eur|inr|aed)\b",
        r"\bconvert\s+to\s+(usd|eur|inr|aed)\b",
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

    match = re.search(r"(\d+(?:\.\d+)?)\s*(usd|eur|inr|aed)", query_lower)
    if match:
        amount = float(match.group(1))
        currency = match.group(2).upper()
        return amount, currency

    match = re.search(r"under\s*(\d+(?:\.\d+)?)\s*(usd|eur|inr|aed)?", query_lower)
    if match:
        amount = float(match.group(1))
        currency = (match.group(2) or "USD").upper()
        return amount, currency

    return 1000.0, "USD"