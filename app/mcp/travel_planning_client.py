import json
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.mcp.base import MCPClientBase, ToolResult

TRAVEL_PLANNING_MCP_URL = "http://127.0.0.1:8000/mcp/mcp"


def _normalize_mcp_result(result: Any) -> dict[str, Any]:
    if result is None:
        return {"raw": None}

    content = getattr(result, "content", None)
    if content:
        texts: list[str] = []
        for block in content:
            text_value = getattr(block, "text", None)
            if text_value:
                texts.append(text_value)

        joined = "\n".join(texts).strip()
        if joined:
            try:
                return json.loads(joined)
            except Exception:
                return {"text": joined}

    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured

    return {"raw": str(result)}


class TravelPlanningMCPClient(MCPClientBase):
    async def call_tool(self, tool_name: str, arguments: dict) -> ToolResult:
        try:
            async with streamable_http_client(TRAVEL_PLANNING_MCP_URL) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools_result = await session.list_tools()
                    available_tools = [tool.name for tool in tools_result.tools]

                    result = await session.call_tool(tool_name, arguments)
                    parsed = _normalize_mcp_result(result)

                    return ToolResult(
                        tool_name=tool_name,
                        content={
                            "result": parsed,
                            "_meta": {
                                "server_url": TRAVEL_PLANNING_MCP_URL,
                                "available_tools": available_tools,
                                "called_tool": tool_name,
                                "arguments": arguments,
                            },
                        },
                    )
        except Exception as exc:
            return ToolResult(
                tool_name=tool_name,
                content={
                    "error": str(exc),
                    "note": "Local travel planning MCP failed.",
                    "_meta": {
                        "server_url": TRAVEL_PLANNING_MCP_URL,
                        "called_tool": tool_name,
                        "arguments": arguments,
                    },
                },
            )