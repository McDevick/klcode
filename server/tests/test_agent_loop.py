import json

import pytest

from kl_server.core.agent_loop import AgentLoop, LoopSettings
from kl_server.core.context import AssembledContext
from kl_server.core.event_logger import EventLogger
from kl_server.core.guardrail import DangerClassifier, Guardrail, HITLManager, ScopeFence
from kl_server.core.sandbox import SandboxPolicy
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
    assert any("missing" in message["content"] for message in second_messages if message["role"] == "feedback")


@pytest.mark.asyncio
async def test_tool_crash_is_reported_back():
    registry = ToolRegistry()
    registry.register(CrashTool())
    loop, provider = make_loop(registry, ['{"tool":"crash","args":{}}', "DONE"])

    result = await loop.run(Session(id="s1", workspace="."), "finish task")

    assert result == "DONE"
    second_messages = provider.calls[1].messages
    assert any("boom" in message["content"] for message in second_messages if message["role"] == "feedback")


class FailingCommandTool(Tool):
    name = "run_command"
    description = "runs a command that fails"
    schema = {"type": "object", "properties": {}}

    async def execute(self, args, ctx: ToolContext) -> ToolResult:
        return ToolResult(ok=True, output='{"exit_code": 1, "stdout": "1 failed", "stderr": ""}')


@pytest.mark.asyncio
async def test_loop_reinjects_feedback_into_history():
    registry = ToolRegistry()
    registry.register(FailingCommandTool())
    provider = MockProvider(responses=['{"tool":"run_command","args":{}}', "DONE"])
    loop = AgentLoop(
        provider=provider,
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=3),
    )
    await loop.run(Session(id="s1", workspace="."), "fix")
    feedback_msgs = [m for m in provider.calls[1].messages if m.get("role") == "feedback"]
    assert feedback_msgs and "test_failure" in feedback_msgs[0]["content"]


class SpyAssembler:
    def __init__(self):
        self.calls = 0
        self.last_kwargs = {}

    async def build(self, **kwargs) -> AssembledContext:
        self.calls += 1
        self.last_kwargs = kwargs
        return AssembledContext(text="assembled", used_tokens=10)


class FakeMemory:
    async def find(self, tags):
        return ["remembered decision"]


@pytest.mark.asyncio
async def test_loop_uses_context_assembler():
    registry = ToolRegistry()
    registry.register(FinalTool())
    provider = MockProvider(responses=['{"tool":"final","args":{}}', "DONE"])
    spy = SpyAssembler()
    loop = AgentLoop(
        provider=provider,
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=3),
        context=spy,
        memory=FakeMemory(),
    )

    await loop.run(Session(id="s1", workspace="."), "task")

    assert spy.calls >= 1
    assert spy.last_kwargs["memory"] == ["remembered decision"]
    assert spy.last_kwargs["task_id"] == "s1"
    assert spy.last_kwargs["tool_catalog"][0]["name"] == "final"
    assert provider.calls[0].messages == [{"role": "user", "content": "assembled"}]


@pytest.mark.asyncio
async def test_loop_writes_events_in_realtime(tmp_path):
    registry = ToolRegistry()
    registry.register(FinalTool())
    provider = MockProvider(responses=['{"tool":"final","args":{}}', "DONE"])
    logger = EventLogger(tmp_path / "audit.jsonl")
    loop = AgentLoop(
        provider=provider,
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=3),
        logger=logger,
    )
    await loop.run(Session(id="s1", workspace="."), "task", task_id="s1")
    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    events = [line.split('"event": "')[1].split('"')[0] for line in lines]
    assert "loop_start" in events and "llm_call" in events and "tool_result" in events and "loop_end" in events


@pytest.mark.asyncio
async def test_loop_logs_ordered_events_with_task_id(tmp_path):
    registry = ToolRegistry()
    registry.register(FinalTool())
    provider = MockProvider(responses=['{"tool":"final","args":{}}', "DONE"])
    logger = EventLogger(tmp_path / "audit.jsonl")
    loop = AgentLoop(
        provider=provider,
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=3),
        logger=logger,
    )
    await loop.run(Session(id="s1", workspace="."), "task")
    records = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()]
    assert all(record["task_id"] == "s1" for record in records)
    event_names = [record["event"] for record in records]
    assert event_names[:2] == ["loop_start", "llm_call"]
    assert "llm_result" in event_names
    assert "tool_result" in event_names
    assert event_names[-1] == "loop_end"


@pytest.mark.asyncio
async def test_loop_logs_invalid_action(tmp_path):
    provider = MockProvider(responses=["not json", "DONE"])
    logger = EventLogger(tmp_path / "audit.jsonl")
    loop = AgentLoop(
        provider=provider,
        tools=ToolExecutor(ToolRegistry()),
        settings=LoopSettings(max_iterations=3),
        logger=logger,
    )
    await loop.run(Session(id="s1", workspace="."), "task")
    records = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()]
    assert any(record["event"] == "invalid_action" for record in records)


class ApprovalShellTool(Tool):
    name = "run_command"
    description = "runs an approval-gated command"
    schema = {"type": "object", "properties": {"command": {"type": "string"}}}

    async def execute(self, args, ctx: ToolContext) -> ToolResult:
        return ToolResult(ok=True, output='{"exit_code": 0, "stdout": "ok", "stderr": ""}')


class ApprovalFinalTool(Tool):
    name = "final"
    description = "returns final marker"
    schema = {"type": "object", "properties": {}}

    async def execute(self, args, ctx: ToolContext) -> ToolResult:
        return ToolResult(ok=True, output="done")


def make_approval_executor(tmp_path):
    registry = ToolRegistry()
    registry.register(ApprovalShellTool())
    registry.register(ApprovalFinalTool())
    guardrail = Guardrail(
        scope=ScopeFence(str(tmp_path)),
        sandbox=SandboxPolicy(allow=[], deny=["rm"]),
        danger=DangerClassifier(),
        hitl=HITLManager(),
    )
    return ToolExecutor(registry, guardrail=guardrail), guardrail


@pytest.mark.asyncio
async def test_approval_suspends_then_resumes(tmp_path):
    executor, guardrail = make_approval_executor(tmp_path)
    provider = MockProvider(
        responses=[
            '{"tool":"run_command","args":{"command":"git push --force"}}',
            '{"tool":"final","args":{}}',
            "DONE",
        ]
    )
    decisions: list[tuple[str, str]] = []

    async def approve(task_id: str, action: dict) -> str:
        decisions.append((task_id, action["action_id"]))
        guardrail.hitl.approve(action["action_id"])
        return "approve"

    loop = AgentLoop(
        provider=provider,
        tools=executor,
        settings=LoopSettings(max_iterations=5),
        on_approval=approve,
    )
    result = await loop.run(Session(id="s1", workspace=str(tmp_path)), "deploy")

    assert result == "DONE"
    assert len(provider.calls) == 3
    assert decisions[0][0] == "s1"


@pytest.mark.asyncio
async def test_approval_without_callback_returns_needs_approval(tmp_path):
    executor, _ = make_approval_executor(tmp_path)
    provider = MockProvider(responses=['{"tool":"run_command","args":{"command":"git push --force"}}'])
    loop = AgentLoop(provider=provider, tools=executor, settings=LoopSettings(max_iterations=5))

    result = await loop.run(Session(id="s1", workspace=str(tmp_path)), "deploy")

    assert result == "NEEDS_APPROVAL"
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_approval_reject_continues_with_feedback(tmp_path):
    executor, guardrail = make_approval_executor(tmp_path)
    provider = MockProvider(
        responses=[
            '{"tool":"run_command","args":{"command":"git push --force"}}',
            "DONE",
        ]
    )

    async def reject(task_id: str, action: dict) -> str:
        guardrail.hitl.reject(action["action_id"])
        return "reject"

    loop = AgentLoop(
        provider=provider,
        tools=executor,
        settings=LoopSettings(max_iterations=5),
        on_approval=reject,
    )
    result = await loop.run(Session(id="s1", workspace=str(tmp_path)), "deploy")

    assert result == "DONE"
    assert len(provider.calls) == 2
    feedback = [m for m in provider.calls[1].messages if m.get("role") == "feedback"]
    assert any("rejected" in message["content"] for message in feedback)


@pytest.mark.asyncio
async def test_approval_abort_stops_loop(tmp_path):
    executor, _ = make_approval_executor(tmp_path)
    provider = MockProvider(
        responses=[
            '{"tool":"run_command","args":{"command":"git push --force"}}',
            "DONE",
        ]
    )

    async def abort(task_id: str, action: dict) -> str:
        return "abort"

    loop = AgentLoop(
        provider=provider,
        tools=executor,
        settings=LoopSettings(max_iterations=5),
        on_approval=abort,
    )
    result = await loop.run(Session(id="s1", workspace=str(tmp_path)), "deploy")

    assert result == "ABORTED"
    assert len(provider.calls) == 1
