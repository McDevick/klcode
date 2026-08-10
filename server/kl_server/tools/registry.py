from typing import Any

from jsonschema import SchemaError, ValidationError, validate

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
            {
                "name": tool.name,
                "description": tool.description,
                "schema": dict(tool.schema),
                "permissions": list(getattr(tool, "permissions", [])),
                "sandbox": dict(getattr(tool, "sandbox", {})),
                "timeout": getattr(tool, "timeout", None),
            }
            for tool in self._tools.values()
        ]

    async def execute(self, name: str, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        tool = self.get(name)
        try:
            validate(instance=args, schema=tool.schema)
        except ValidationError as exc:
            return ToolResult(ok=False, output="", error=f"schema_error: {exc.message}")
        except SchemaError as exc:
            return ToolResult(
                ok=False,
                output="",
                error=f"schema_error: invalid schema: {exc.message}",
            )
        return await tool.execute(args, ctx)
