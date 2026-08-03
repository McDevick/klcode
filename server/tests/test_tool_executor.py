import pytest
from kl_server.models.action import ToolResult
from kl_server.tools.base import Tool, ToolContext
from kl_server.tools.registry import ToolRegistry
from kl_server.core.tool_executor import ToolExecutor


class CrashTool(Tool):
    name = "crash"
    description = "always crashes"
    schema = {"type": "object", "properties": {}}

    async def execute(self, args, ctx: ToolContext) -> ToolResult:
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_crash_returns_tool_error():
    registry = ToolRegistry()
    registry.register(CrashTool())
    executor = ToolExecutor(registry)
    result = await executor.execute("crash", {}, ToolContext(workspace="."))
    assert result.ok is False
    assert result.error == "boom"
