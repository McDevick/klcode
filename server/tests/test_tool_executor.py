import asyncio

import pytest
from kl_server.core.guardrail import DangerClassifier, Guardrail, HITLManager, ScopeFence
from kl_server.core.sandbox import SandboxPolicy
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


class BigExceptionTool(Tool):
    name = "big_exception"
    description = "raises a huge error message"
    schema = {"type": "object", "properties": {}}

    async def execute(self, args, ctx: ToolContext) -> ToolResult:
        raise RuntimeError("e" * 100_000)


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


class BigErrorTool(Tool):
    name = "big_error"
    description = "returns huge error"
    schema = {"type": "object", "properties": {}}

    async def execute(self, args, ctx: ToolContext) -> ToolResult:
        return ToolResult(ok=False, output="", error="e" * 100_000)


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
    assert result.error is None


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
    assert result.output.endswith("\n...[truncated]")
    assert result.output.startswith("x")
    assert result.ok is True


class FakeSummarizer:
    async def summarize(self, tool, args, result, task_id):
        return "summarized output"


@pytest.mark.asyncio
async def test_executor_attaches_summary_for_large_output():
    registry = ToolRegistry()
    registry.register(BigTool())
    executor = ToolExecutor(
        registry,
        max_output_chars=10_000,
        summarizer=FakeSummarizer(),
    )

    result = await executor.execute("big", {}, ToolContext(workspace="."))

    assert result.summary == "summarized output"
    assert result.truncated is True
    assert result.output.startswith("x")
    assert result.output.endswith("\n...[truncated]")


@pytest.mark.asyncio
async def test_executor_truncates_large_error():
    registry = ToolRegistry()
    registry.register(BigErrorTool())
    executor = ToolExecutor(registry, max_output_chars=100)
    result = await executor.execute("big_error", {}, ToolContext(workspace="."))
    assert len(result.error) == 100
    assert result.error.endswith("\n...[truncated]")
    assert result.error.startswith("e")
    assert result.ok is False


@pytest.mark.asyncio
async def test_executor_times_out_slow_tool():
    registry = ToolRegistry()
    registry.register(SlowTool())
    executor = ToolExecutor(registry, timeout=0.05)
    result = await executor.execute("slow", {}, ToolContext(workspace="."))
    assert result.ok is False
    assert result.error == "timeout"


@pytest.mark.asyncio
async def test_executor_truncates_large_exception_message():
    registry = ToolRegistry()
    registry.register(BigExceptionTool())
    executor = ToolExecutor(registry, max_output_chars=100)
    result = await executor.execute("big_exception", {}, ToolContext(workspace="."))
    assert len(result.error) == 100
    assert result.error.endswith("\n...[truncated]")
    assert result.error.startswith("e")


class WriteTool(Tool):
    name = "write_file"
    description = "writes a file"
    schema = {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}}

    async def execute(self, args, ctx: ToolContext) -> ToolResult:
        return ToolResult(ok=True, output="wrote")


def make_guardrail(tmp_path):
    return Guardrail(
        scope=ScopeFence(str(tmp_path)),
        sandbox=SandboxPolicy(allow=[], deny=["rm"]),
        danger=DangerClassifier(),
        hitl=HITLManager(),
    )


@pytest.mark.asyncio
async def test_executor_rejects_out_of_scope(tmp_path):
    registry = ToolRegistry()
    registry.register(WriteTool())
    executor = ToolExecutor(registry, guardrail=make_guardrail(tmp_path))
    result = await executor.execute("write_file", {"path": "../x", "content": "hi"}, ToolContext(workspace=str(tmp_path)))
    assert result.ok is False
    assert result.error == "rejected"


@pytest.mark.asyncio
async def test_executor_returns_requires_approval(tmp_path):
    registry = ToolRegistry()
    registry.register(WriteTool())
    executor = ToolExecutor(registry, guardrail=make_guardrail(tmp_path))
    result = await executor.execute("run_command", {"command": "git push --force"}, ToolContext(workspace=str(tmp_path)))
    assert result.ok is False
    assert result.error == "requires_approval"
    assert result.meta["tool"] == "run_command"
    assert result.meta["args"] == {"command": "git push --force"}


@pytest.mark.asyncio
async def test_executor_allows_safe_action_and_does_not_run_rejected(tmp_path):
    registry = ToolRegistry()
    registry.register(WriteTool())
    executor = ToolExecutor(registry, guardrail=make_guardrail(tmp_path))
    safe = await executor.execute("write_file", {"path": "a.txt", "content": "hi"}, ToolContext(workspace=str(tmp_path)))
    assert safe.ok is True
    rejected = await executor.execute("write_file", {"path": "../x", "content": "hi"}, ToolContext(workspace=str(tmp_path)))
    assert rejected.ok is False
    assert rejected.error == "rejected"


@pytest.mark.asyncio
async def test_executor_isolates_guardrail_errors(tmp_path):
    class ExplodingGuardrail:
        def check(self, action):
            raise RuntimeError("guardrail boom")

    registry = ToolRegistry()
    registry.register(WriteTool())
    executor = ToolExecutor(registry, guardrail=ExplodingGuardrail())
    result = await executor.execute("write_file", {"path": "a.txt", "content": "hi"}, ToolContext(workspace=str(tmp_path)))
    assert result.ok is False
    assert "guardrail_error" in result.error


@pytest.mark.asyncio
async def test_executor_uses_workspace_mode_from_context(tmp_path):
    registry = ToolRegistry()
    registry.register(WriteTool())
    executor = ToolExecutor(registry, guardrail=make_guardrail(tmp_path))
    ctx = ToolContext(workspace=str(tmp_path), workspace_mode="unmanaged")
    result = await executor.execute("write_file", {"path": "a.py", "content": "x"}, ctx)
    assert result.ok is False
    assert result.error == "requires_approval"


class TrackingWriteTool(Tool):
    name = "write_file"
    description = "tracks approval-gated writes"
    schema = {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}}

    def __init__(self):
        self.calls = 0

    async def execute(self, args, ctx: ToolContext) -> ToolResult:
        self.calls += 1
        return ToolResult(ok=True, output="wrote")


@pytest.mark.asyncio
async def test_executor_requires_approval_meta_is_deterministic(tmp_path):
    hitl = HITLManager()
    guardrail = Guardrail(
        scope=ScopeFence(str(tmp_path)),
        sandbox=SandboxPolicy(allow=[], deny=["rm"]),
        danger=DangerClassifier(),
        hitl=hitl,
    )
    executor = ToolExecutor(ToolRegistry(), guardrail=guardrail)
    ctx = ToolContext(workspace=str(tmp_path), task_id="t1")

    first = await executor.execute("run_command", {"command": "git push --force"}, ctx)
    second = await executor.execute("run_command", {"command": "git push --force"}, ctx)

    assert first.error == "requires_approval"
    assert first.meta["action_id"] == second.meta["action_id"]
    assert first.meta["tool"] == "run_command"
    assert first.meta["args"] == {"command": "git push --force"}
    assert first.meta["level"] == "critical"
    assert first.meta["action_id"] in hitl.requests
    assert len(hitl.requests) == 1


@pytest.mark.asyncio
async def test_execute_approved_only_runs_after_hitl_approval(tmp_path):
    tool = TrackingWriteTool()
    registry = ToolRegistry()
    registry.register(tool)
    hitl = HITLManager()
    guardrail = Guardrail(
        scope=ScopeFence(str(tmp_path)),
        sandbox=SandboxPolicy(allow=[], deny=["rm"]),
        danger=DangerClassifier(),
        hitl=hitl,
    )
    executor = ToolExecutor(registry, guardrail=guardrail)
    ctx = ToolContext(workspace=str(tmp_path), task_id="t1", workspace_mode="unmanaged")
    args = {"path": "a.py", "content": "x"}

    requested = await executor.execute("write_file", args, ctx)
    assert requested.error == "requires_approval"

    denied = await executor.execute_approved("write_file", args, ctx, "missing")
    assert denied.error == "not_approved"

    pending = await executor.execute_approved("write_file", args, ctx, requested.meta["action_id"])
    assert pending.error == "not_approved"
    assert tool.calls == 0

    hitl.approve(requested.meta["action_id"])
    approved = await executor.execute_approved("write_file", args, ctx, requested.meta["action_id"])

    assert approved.ok is True
    assert tool.calls == 1
