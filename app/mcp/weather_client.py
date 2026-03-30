import json
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from app.mcp.base import MCPClientBase, ToolResult


def _normalize_mcp_result(result: Any) -> dict[str, Any]:
    if result is None:
        return {"raw": None}

    content = getattr(result, "content", None)
    if content:
        texts = []
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

    return {"raw": str(result)}


class WeatherMCPClient(MCPClientBase):
    async def call_tool(self, tool_name: str, arguments: dict) -> ToolResult:
        server_params = StdioServerParameters(
            command="poetry",
            args=["run", "python", "-m", "mcp_weather_server"],
        )

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                tools_result = await session.list_tools()
                print("[Weather MCP Tools]", tools_result)

                result = await session.call_tool(tool_name, arguments)
                parsed = _normalize_mcp_result(result)
                print("[Weather MCP Parsed Result]", parsed)

        return ToolResult(
            tool_name=tool_name,
            content=parsed,
        )