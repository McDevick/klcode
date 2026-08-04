import asyncio

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


class EmptyMessageCrashTool(Tool):
    name = "empty_crash"
    description = "crashes without a message"
    schema = {"type": "object", "properties": {}}

    async def execute(self, args, ctx: ToolContext) -> ToolResult:
        raise RuntimeError()


class SuccessTool(Tool):
    name = "success"
    description = "always succeeds"
    schema = {"type": "object", "properties": {}}

    async def execute(self, args, ctx: ToolContext) -> ToolResult:
        return ToolResult(ok=True, output="ok")


class CancelledTool(Tool):
    name = "cancel"
    description = "always cancels"
    schema = {"type": "object", "properties": {}}

    async def execute(self, args, ctx: ToolContext) -> ToolResult:
        raise asyncio.CancelledError()


class BigTool(Tool):
    name = "big"
    description = "returns huge output"
    schema = {"type": "object", "properties": {}}

    async def execute(self, args, ctx: ToolContext) -> ToolResult:
        return ToolResult(ok=True, output="x" * 100_000)


class SlowTool(Tool):
    name = "slow"
    description = "sleeps too long"
    schema = {"type": "object", "properties": {}}

    async def execute(self, args, ctx: ToolContext) -> ToolResult:
        await asyncio.sleep(1)
        return ToolResult(ok=True, output="late")


@pytest.mark.asyncio
async def test_crash_returns_tool_error():
    registry = ToolRegistry()
    registry.register(CrashTool())
    executor = ToolExecutor(registry)
    result = await executor.execute("crash", {}, ToolContext(workspace="."))
    assert result.ok is False
    assert result.output == ""
    assert result.error == "boom"


@pytest.mark.asyncio
async def test_crash_without_message_uses_exception_name():
    registry = ToolRegistry()
    registry.register(EmptyMessageCrashTool())
    executor = ToolExecutor(registry)

    result = await executor.execute("empty_crash", {}, ToolContext(workspace="."))

    assert result.ok is False
    assert result.output == ""
    assert result.error == "RuntimeError"


@pytest.mark.asyncio
async def test_success_is_returned_unchanged():
    registry = ToolRegistry()
    registry.register(SuccessTool())
    executor = ToolExecutor(registry)

    result = await executor.execute("success", {}, ToolContext(workspace="."))

    assert result is not None
    assert result.ok is True
    assert result.output == "ok"


@pytest.mark.asyncio
async def test_unknown_tool_returns_error():
    executor = ToolExecutor(ToolRegistry())

    result = await executor.execute("missing", {}, ToolContext(workspace="."))

    assert result.ok is False
    assert result.error


@pytest.mark.asyncio
async def test_cancelled_error_propagates():
    registry = ToolRegistry()
    registry.register(CancelledTool())
    executor = ToolExecutor(registry)

    with pytest.raises(asyncio.CancelledError):
        await executor.execute("cancel", {}, ToolContext(workspace="."))


@pytest.mark.asyncio
async def test_executor_truncates_large_output():
    registry = ToolRegistry()
    registry.register(BigTool())
    executor = ToolExecutor(registry, max_output_chars=10_000)
    result = await executor.execute("big", {}, ToolContext(workspace="."))
    assert len(result.output) == 10_000


@pytest.mark.asyncio
async def test_executor_times_out_slow_tool():
    registry = ToolRegistry()
    registry.register(SlowTool())
    executor = ToolExecutor(registry, timeout=0.05)
    result = await executor.execute("slow", {}, ToolContext(workspace="."))
    assert result.ok is False
    assert result.error == "timeout"
