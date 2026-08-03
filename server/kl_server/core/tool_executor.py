from kl_server.models.action import ToolResult
from kl_server.tools.base import ToolContext
from kl_server.tools.registry import ToolRegistry


class ToolExecutor:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def execute(self, name: str, args: dict, ctx: ToolContext) -> ToolResult:
        try:
            return await self.registry.execute(name, args, ctx)
        except Exception as exc:
            return ToolResult(ok=False, output="", error=str(exc))
