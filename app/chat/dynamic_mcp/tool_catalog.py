import asyncio
from typing import Any

from app.mcp.currency_client import CurrencyMCPClient
from app.mcp.travel_planning_client import TravelPlanningMCPClient
from app.mcp.weather_client import WeatherMCPClient

weather_client = WeatherMCPClient()
currency_client = CurrencyMCPClient()
travel_planning_client = TravelPlanningMCPClient()


def _dedupe_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []

    for tool in tools:
        key = (tool.get("mcp_family", ""), tool.get("tool_name", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(tool)

    return deduped


async def discover_live_tool_catalog() -> list[dict[str, Any]]:
    results = await asyncio.gather(
        travel_planning_client.list_tools(),
        weather_client.list_tools(),
        currency_client.list_tools(),
        return_exceptions=True,
    )

    tools: list[dict[str, Any]] = []
    for result in results:
        if isinstance(result, Exception):
            continue
        tools.extend(result)

    return _dedupe_tools(tools)


def get_tool_spec(
    available_tools: list[dict[str, Any]],
    tool_name: str,
) -> dict[str, Any] | None:
    for tool in available_tools:
        if tool.get("tool_name") == tool_name:
            return tool
    return None


def get_required_args(
    available_tools: list[dict[str, Any]],
    tool_name: str,
) -> list[str]:
    spec = get_tool_spec(available_tools, tool_name)
    if not spec:
        return []
    return list(spec.get("required_args", []))