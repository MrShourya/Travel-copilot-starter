from typing import Any


DYNAMIC_MCP_TOOLS: dict[str, dict[str, Any]] = {
    "trip_readiness_check_tool": {
        "mcp_family": "travel_planning_mcp",
        "description": (
            "Checks whether enough trip information is available to proceed. "
            "Useful before creating an itinerary or trip summary."
        ),
        "required_args": [],
        "optional_args": ["city", "trip_days", "date_text", "budget_amount"],
    },
    "build_trip_summary_tool": {
        "mcp_family": "travel_planning_mcp",
        "description": (
            "Builds a trip summary when city and trip_days are known. "
            "Can also use date_text, budget, currencies, and travel_style."
        ),
        "required_args": ["city", "trip_days"],
        "optional_args": [
            "date_text",
            "budget_amount",
            "budget_currency",
            "target_currency",
            "travel_style",
        ],
    },
    "estimate_daily_budget_tool": {
        "mcp_family": "travel_planning_mcp",
        "description": (
            "Estimates the daily budget and total budget for a trip."
        ),
        "required_args": ["city", "trip_days"],
        "optional_args": ["travel_style", "currency"],
    },
    "suggest_packing_list_tool": {
        "mcp_family": "travel_planning_mcp",
        "description": (
            "Suggests a packing list using city, season, and trip duration."
        ),
        "required_args": ["city", "season", "trip_days"],
        "optional_args": [],
    },
    "get_current_weather": {
        "mcp_family": "weather_mcp",
        "description": "Gets current weather for a city.",
        "required_args": ["city"],
        "optional_args": [],
    },
    "get_weather_byDateTimeRange": {
        "mcp_family": "weather_mcp",
        "description": (
            "Gets weather for a city across a start_date and end_date."
        ),
        "required_args": ["city", "start_date", "end_date"],
        "optional_args": [],
    },
    "get_latest_rates": {
        "mcp_family": "currency_mcp",
        "description": "Gets latest currency exchange rates.",
        "required_args": ["base", "symbols"],
        "optional_args": [],
    },
}


def get_tool_spec(tool_name: str) -> dict[str, Any] | None:
    return DYNAMIC_MCP_TOOLS.get(tool_name)


def list_tools_for_prompt() -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for tool_name, spec in DYNAMIC_MCP_TOOLS.items():
        tools.append(
            {
                "tool_name": tool_name,
                "mcp_family": spec["mcp_family"],
                "description": spec["description"],
                "required_args": spec["required_args"],
                "optional_args": spec["optional_args"],
            }
        )
    return tools


def get_required_args(tool_name: str) -> list[str]:
    spec = get_tool_spec(tool_name)
    if not spec:
        return []
    return list(spec.get("required_args", []))