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

    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured

    return {"raw": str(result)}


def _normalize_tool(tool: Any) -> dict[str, Any]:
    input_schema = getattr(tool, "inputSchema", None) or {}
    properties = input_schema.get("properties", {}) if isinstance(input_schema, dict) else {}
    required = input_schema.get("required", []) if isinstance(input_schema, dict) else []

    return {
        "tool_name": getattr(tool, "name", ""),
        "mcp_family": "weather_mcp",
        "description": getattr(tool, "description", "") or "",
        "required_args": list(required),
        "optional_args": [k for k in properties.keys() if k not in required],
        "input_schema": input_schema,
    }


class WeatherMCPClient(MCPClientBase):
    def _server_params(self) -> StdioServerParameters:
        return StdioServerParameters(
            command="poetry",
            args=["run", "python", "-m", "mcp_weather_server"],
        )

    async def list_tools(self) -> list[dict[str, Any]]:
        try:
            async with stdio_client(self._server_params()) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools_result = await session.list_tools()
                    return [_normalize_tool(tool) for tool in tools_result.tools]
        except Exception:
            return []

    async def call_tool(self, tool_name: str, arguments: dict) -> ToolResult:
        try:
            async with stdio_client(self._server_params()) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
                    parsed = _normalize_mcp_result(result)
                    return ToolResult(
                        tool_name=tool_name,
                        content=parsed,
                    )
        except Exception as exc:
            return ToolResult(
                tool_name=tool_name,
                content={
                    "error": str(exc),
                    "note": "Weather MCP failed.",
                },
            )