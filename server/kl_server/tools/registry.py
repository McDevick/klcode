from typing import Any

from kl_server.models.action import ToolResult
from kl_server.tools.base import Tool, ToolContext


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool; later registrations with the same name replace earlier ones."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        return self._tools[name]

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def catalog(self) -> list[dict[str, Any]]:
        return [
            {"name": tool.name, "description": tool.description, "schema": dict(tool.schema)}
            for tool in self._tools.values()
        ]

    async def execute(self, name: str, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await self.get(name).execute(args, ctx)
