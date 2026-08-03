import pytest
from kl_server.core.agent_loop import AgentLoop, LoopSettings
from kl_server.core.tool_executor import ToolExecutor
from kl_server.models.action import ToolResult
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


class CrashTool(Tool):
    name = "crash"
    description = "always crashes"
    schema = {"type": "object", "properties": {}}

    async def execute(self, args, ctx: ToolContext) -> ToolResult:
        raise RuntimeError("boom")


def make_loop(registry: ToolRegistry, responses: list[str], max_iterations: int = 3):
    provider = MockProvider(responses=responses)
    loop = AgentLoop(
        provider=provider,
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=max_iterations),
    )
    return loop, provider


@pytest.mark.asyncio
async def test_loop_runs_tool_and_stops():
    registry = ToolRegistry()
    registry.register(FinalTool())
    loop, provider = make_loop(registry, ['{"tool":"final","args":{}}', "DONE"])
    result = await loop.run(Session(id="s1", workspace="."), "finish task")
    assert result == "DONE"
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_loop_stops_at_max_iterations():
    loop, provider = make_loop(ToolRegistry(), ["not json", "not json"], max_iterations=2)

    result = await loop.run(Session(id="s1", workspace="."), "finish task")

    assert result == "MAX_ITERATIONS"
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_loop_skips_malformed_valid_json():
    loop, provider = make_loop(ToolRegistry(), ["{}", "DONE"])

    result = await loop.run(Session(id="s1", workspace="."), "finish task")

    assert result == "DONE"
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_unknown_tool_is_reported_back():
    loop, provider = make_loop(ToolRegistry(), ['{"tool":"missing","args":{}}', "DONE"])

    result = await loop.run(Session(id="s1", workspace="."), "finish task")

    assert result == "DONE"
    second_messages = provider.calls[1].messages
    assert any("missing" in message["content"] for message in second_messages if message["role"] == "system")


@pytest.mark.asyncio
async def test_tool_crash_is_reported_back():
    registry = ToolRegistry()
    registry.register(CrashTool())
    loop, provider = make_loop(registry, ['{"tool":"crash","args":{}}', "DONE"])

    result = await loop.run(Session(id="s1", workspace="."), "finish task")

    assert result == "DONE"
    second_messages = provider.calls[1].messages
    assert any("boom" in message["content"] for message in second_messages if message["role"] == "system")
