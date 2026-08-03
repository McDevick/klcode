from typing import Any

from kl_server.models.action import ToolResult
from kl_server.tools.base import ToolContext
from kl_server.tools.registry import ToolRegistry


class ToolExecutor:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def execute(self, name: str, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            return await self.registry.execute(name, args, ctx)
        except Exception as exc:
            message = str(exc) or type(exc).__name__
            return ToolResult(ok=False, output="", error=message)
