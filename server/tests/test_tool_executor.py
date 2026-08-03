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
