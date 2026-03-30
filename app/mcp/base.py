from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    tool_name: str
    content: dict[str, Any]


class MCPClientBase:
    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        raise NotImplementedError