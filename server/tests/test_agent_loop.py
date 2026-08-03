import pytest
from kl_server.core.agent_loop import AgentLoop, LoopSettings
from kl_server.models.action import Action, ToolResult
from kl_server.models.task import Session
from kl_server.providers.mock import MockProvider
from kl_server.tools.base import Tool, ToolContext
from kl_server.tools.registry import ToolRegistry


class FinalTool(Tool):
    name = "final"
    description = "returns final marker"
    schema = {"type": "object", "properties": {}}

    async def execute(self, args, ctx: ToolContext) -> ToolResult:
        return ToolResult(ok=True, output="done")


@pytest.mark.asyncio
async def test_loop_runs_tool_and_stops():
    registry = ToolRegistry()
    registry.register(FinalTool())
    provider = MockProvider(responses=['{"tool":"final","args":{}}', "DONE"])
    loop = AgentLoop(provider=provider, tools=registry, settings=LoopSettings(max_iterations=3))
    result = await loop.run(Session(id="s1", workspace="."), "finish task")
    assert result == "DONE"
    assert len(provider.calls) == 2
