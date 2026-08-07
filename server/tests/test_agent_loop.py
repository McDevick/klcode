import json

import pytest

from kl_server.core.agent_loop import AgentLoop, LoopSettings
from kl_server.core.context import AssembledContext
from kl_server.core.event_logger import EventLogger
from kl_server.core.guardrail import DangerClassifier, Guardrail, HITLManager, ScopeFence
from kl_server.core.sandbox import SandboxPolicy
from kl_server.core.tool_executor import ToolExecutor
from kl_server.memory.store import MemoryStore
from kl_server.models.action import ToolResult
from kl_server.models.task import Session
from kl_server.providers.base import ProviderResponse, ProviderToolCall
from kl_server.providers.mock import MockProvider
from kl_server.providers.registry import ProviderRegistry
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


class FailingProvider:
    async def complete(self, request):
        raise RuntimeError("api down")


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
    registry = ToolRegistry()
    registry.register(FinalTool())
    loop, provider = make_loop(
        registry,
        ['{"tool":"final","args":{}}', '{"tool":"final","args":{}}'],
        max_iterations=2,
    )

    result = await loop.run(Session(id="s1", workspace="."), "finish task")

    assert result == "MAX_ITERATIONS"
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_loop_treats_json_without_tool_as_final_answer():
    """原生格式下无 tool 字段的 JSON 不是动作：整体作为最终回答结束循环。"""
    loop, provider = make_loop(ToolRegistry(), ["{}"])

    result = await loop.run(Session(id="s1", workspace="."), "finish task")

    assert result == "{}"
    assert len(provider.calls) == 1


def _feedback_messages(messages: list[dict]) -> list[dict]:
    """收集注入的反馈消息（原生格式下 feedback 为 user 消息）。"""
    return [
        message
        for message in messages
        if message.get("role") == "user"
        and str(message.get("content", "")).startswith("feedback")
    ]


@pytest.mark.asyncio
async def test_unknown_tool_is_reported_back():
    loop, provider = make_loop(ToolRegistry(), ['{"tool":"missing","args":{}}', "DONE"])

    result = await loop.run(Session(id="s1", workspace="."), "finish task")

    assert result == "DONE"
    second_messages = provider.calls[1].messages
    assert any("missing" in message["content"] for message in _feedback_messages(second_messages))


@pytest.mark.asyncio
async def test_tool_crash_is_reported_back():
    registry = ToolRegistry()
    registry.register(CrashTool())
    loop, provider = make_loop(registry, ['{"tool":"crash","args":{}}', "DONE"])

    result = await loop.run(Session(id="s1", workspace="."), "finish task")

    assert result == "DONE"
    second_messages = provider.calls[1].messages
    assert any("boom" in message["content"] for message in _feedback_messages(second_messages))


class FailingTestTool(Tool):
    name = "run_tests"
    description = "runs tests that fail"
    schema = {"type": "object", "properties": {}}

    async def execute(self, args, ctx: ToolContext) -> ToolResult:
        return ToolResult(ok=True, output='{"exit_code": 1, "stdout": "1 failed", "stderr": ""}')


class LongFailingTestTool(Tool):
    name = "run_tests"
    description = "returns a long test failure"
    schema = {"type": "object", "properties": {}}

    async def execute(self, args, ctx: ToolContext) -> ToolResult:
        return ToolResult(
            ok=True,
            output=(
                '{"exit_code": 1, "stdout": "'
                + "x" * 2000
                + ' FINAL FAILED", "stderr": ""}'
            ),
        )


class BigOutputTool(Tool):
    name = "big_output"
    description = "returns a large output"
    schema = {"type": "object", "properties": {}}

    async def execute(self, args, ctx: ToolContext) -> ToolResult:
        return ToolResult(ok=True, output="x" * 100_000)


class FakeToolSummarizer:
    async def summarize(self, tool, args, result, task_id):
        return "summarized tool output"


@pytest.mark.asyncio
async def test_loop_reinjects_feedback_into_history():
    registry = ToolRegistry()
    registry.register(FailingTestTool())
    provider = MockProvider(responses=['{"tool":"run_tests","args":{}}', "DONE"])
    loop = AgentLoop(
        provider=provider,
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=3),
    )
    await loop.run(Session(id="s1", workspace="."), "fix")
    feedback_msgs = _feedback_messages(provider.calls[1].messages)
    assert feedback_msgs and "test_failure" in feedback_msgs[0]["content"]


@pytest.mark.asyncio
async def test_loop_injects_retry_budget_signal():
    registry = ToolRegistry()
    registry.register(FailingTestTool())
    provider = MockProvider(
        responses=[
            '{"tool":"run_tests","args":{}}',
            '{"tool":"run_tests","args":{}}',
            "DONE",
        ]
    )
    loop = AgentLoop(
        provider=provider,
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=5, retry_budget=2),
    )

    await loop.run(Session(id="s1", workspace="."), "fix")

    third_messages = provider.calls[2].messages
    assert any(
        "retry_budget_exhausted" in message["content"]
        for message in _feedback_messages(third_messages)
    )


@pytest.mark.asyncio
async def test_loop_memory_keeps_feedback_tail(tmp_path):
    registry = ToolRegistry()
    registry.register(LongFailingTestTool())
    provider = MockProvider(responses=['{"tool":"run_tests","args":{}}', "DONE"])
    memory = MemoryStore(tmp_path / "memory.db")
    loop = AgentLoop(
        provider=provider,
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=3),
        memory=memory,
    )

    await loop.run(Session(id="s1", workspace="."), "fix")

    feedback_records = await memory.list_by_kind("s1", "feedback")
    assert feedback_records[-1]["content"].endswith("FINAL FAILED")


@pytest.mark.asyncio
async def test_loop_uses_tool_summary_in_history():
    registry = ToolRegistry()
    registry.register(BigOutputTool())
    executor = ToolExecutor(registry, summarizer=FakeToolSummarizer())
    provider = MockProvider(responses=['{"tool":"big_output","args":{}}', "DONE"])
    loop = AgentLoop(
        provider=provider,
        tools=executor,
        settings=LoopSettings(max_iterations=3),
    )

    await loop.run(Session(id="s1", workspace="."), "task")

    second_messages = provider.calls[1].messages
    tool_messages = [
        message
        for message in second_messages
        if message.get("role") == "tool"
    ]
    assert tool_messages
    assert tool_messages[0]["content"] == "summarized tool output"


class SpyAssembler:
    def __init__(self):
        self.calls = 0
        self.last_kwargs = {}

    async def build(self, **kwargs) -> AssembledContext:
        self.calls += 1
        self.last_kwargs = kwargs
        return AssembledContext(text="assembled", used_tokens=10)

    def should_compress(self, history: list[str]) -> bool:
        return False

    async def compact_history(self, history: list[str], task_id: str) -> str:
        return ""


class CompressContext:
    async def build(self, **kwargs) -> AssembledContext:
        return AssembledContext(text="compiled", used_tokens=10)

    def should_compress(self, history: list[str]) -> bool:
        return bool(history)

    async def compact_history(self, history: list[str], task_id: str) -> str:
        return "compressed summary"


class FakeMemory:
    def __init__(self):
        self.added: list[tuple[str, str, list[str], str]] = []

    async def find(self, tags):
        return ["remembered decision"]

    async def add(self, scope, kind, tags, content):
        self.added.append((scope, kind, list(tags), content))


class RecordingMemory:
    def __init__(self):
        self.added: list[tuple[str, str, list[str], str]] = []

    async def find(self, tags):
        return []

    async def add(self, scope, kind, tags, content):
        self.added.append((scope, kind, list(tags), content))


@pytest.mark.asyncio
async def test_loop_writes_task_and_tool_results_to_memory():
    registry = ToolRegistry()
    registry.register(FinalTool())
    provider = MockProvider(responses=['{"tool":"final","args":{}}', "DONE"])
    memory = RecordingMemory()
    loop = AgentLoop(
        provider=provider,
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=3),
        memory=memory,
    )

    await loop.run(Session(id="s1", workspace="."), "remember this task")

    kinds = [record[1] for record in memory.added]
    assert "task" in kinds
    assert "tool_result" in kinds
    task_record = next(record for record in memory.added if record[1] == "task")
    assert task_record[0] == "s1"
    assert "s1" in task_record[2]
    tool_record = next(record for record in memory.added if record[1] == "tool_result")
    assert "final" in tool_record[3]


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
    # 工具目录通过 OpenAI tools 请求参数传递（含 schema），不再进上下文
    tools = provider.calls[0].tools
    assert tools is not None
    assert tools[0]["function"]["name"] == "final"
    # 规则/记忆作为 system 上下文注入，原生 role 历史完整保留在后面。
    assert provider.calls[0].messages[0]["role"] == "system"
    system_messages = [
        message
        for message in provider.calls[0].messages
        if message["role"] == "system"
    ]
    assert any(message.get("content") == "assembled" for message in system_messages)
    assert any(
        message.get("role") == "user" and message.get("content") == "task"
        for message in provider.calls[0].messages
    )


@pytest.mark.asyncio
async def test_loop_context_preserves_role_labels():
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

    assert spy.last_kwargs["history"] == []
    messages = provider.calls[1].messages
    assert any(message["role"] == "assistant" and "tool_calls" in message for message in messages)
    assert any(message["role"] == "tool" for message in messages)


@pytest.mark.asyncio
async def test_loop_injects_compressed_context_summary():
    registry = ToolRegistry()
    registry.register(FinalTool())
    provider = MockProvider(
        responses=['{"tool":"final","args":{}}', '{"tool":"final","args":{}}', "DONE"]
    )
    loop = AgentLoop(
        provider=provider,
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=4),
        context=CompressContext(),
    )

    await loop.run(Session(id="s1", workspace="."), "task")

    first_messages = provider.calls[0].messages
    assert any(
        "Previous context summary" in str(message.get("content", ""))
        for message in first_messages
    )


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
async def test_provider_error_writes_feedback_generation(tmp_path):
    logger = EventLogger(tmp_path / "audit.jsonl")
    loop = AgentLoop(
        provider=FailingProvider(),
        tools=ToolExecutor(ToolRegistry()),
        settings=LoopSettings(max_iterations=2),
        logger=logger,
    )

    with pytest.raises(RuntimeError, match="api down"):
        await loop.run(Session(id="s1", workspace="."), "task", task_id="s1")

    records = [
        json.loads(line)
        for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    ]
    feedback_events = [
        record for record in records if record["event"] == "feedback_generation"
    ]
    assert feedback_events
    assert feedback_events[-1]["payload"]["category"] == "provider_error"


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
    assert "feedback_generation" in event_names
    assert event_names[-1] == "loop_end"


@pytest.mark.asyncio
async def test_loop_forwards_provider_default_model_for_mock_placeholder():
    """Sessions default to model='mock-model'; real providers should receive
    their configured default model instead of the mock placeholder."""
    registry = ToolRegistry()
    registry.register(FinalTool())
    provider = MockProvider(responses=["DONE"])
    provider.model = "deepseek-chat"
    loop = AgentLoop(
        provider=provider,
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=2),
    )

    await loop.run(Session(id="s1", workspace="."), "task")

    assert provider.calls[0].model == "deepseek-chat"


@pytest.mark.asyncio
async def test_loop_keeps_explicit_session_model():
    provider = MockProvider(responses=["DONE"])
    loop = AgentLoop(
        provider=provider,
        tools=ToolExecutor(ToolRegistry()),
        settings=LoopSettings(max_iterations=2),
    )

    await loop.run(Session(id="s1", workspace=".", model="gpt-test"), "task")

    assert provider.calls[0].model == "gpt-test"


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
    # 拒绝结果通过 tool 消息回传给模型
    tool_messages = [m for m in provider.calls[1].messages if m.get("role") == "tool"]
    assert any("rejected" in message["content"] for message in tool_messages)


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


@pytest.mark.asyncio
async def test_loop_resolves_provider_from_registry_by_current_default():
    registry = ToolRegistry()
    registry.register(FinalTool())
    providers = ProviderRegistry()
    provider_a = MockProvider(responses=['{"tool":"final","args":{}}', "DONE"])
    provider_b = MockProvider(responses=['{"tool":"final","args":{}}', "DONE"])
    providers.register("a", provider_a)
    providers.register("b", provider_b)
    current = {"name": "a"}
    loop = AgentLoop(
        provider=MockProvider(responses=["DONE"]),  # 兜底，不应被使用
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=3),
        provider_registry=providers,
        default_provider=lambda: current["name"],
        default_model=lambda: "",
    )

    await loop.run(Session(id="s1", workspace="."), "finish task")

    assert len(provider_a.calls) == 2
    assert len(provider_b.calls) == 0

    current["name"] = "b"
    await loop.run(Session(id="s2", workspace="."), "finish task")

    assert len(provider_a.calls) == 2
    assert len(provider_b.calls) == 2


@pytest.mark.asyncio
async def test_loop_uses_global_default_model_when_session_is_mock_placeholder():
    registry = ToolRegistry()
    registry.register(FinalTool())
    providers = ProviderRegistry()
    provider = MockProvider(responses=["DONE"])
    provider.model = "provider-model"
    providers.register("p", provider)
    loop = AgentLoop(
        provider=MockProvider(responses=["DONE"]),
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=2),
        provider_registry=providers,
        default_provider=lambda: "p",
        default_model=lambda: "global-model",
    )

    await loop.run(Session(id="s1", workspace="."), "task")

    assert provider.calls[0].model == "global-model"


@pytest.mark.asyncio
async def test_loop_uses_current_provider_model_when_session_provider_differs():
    registry = ToolRegistry()
    registry.register(FinalTool())
    providers = ProviderRegistry()
    provider = MockProvider(responses=["DONE"])
    provider.model = "current-provider-model"
    providers.register("p", provider)
    loop = AgentLoop(
        provider=MockProvider(responses=["DONE"]),
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=2),
        provider_registry=providers,
        default_provider=lambda: "p",
        default_model=lambda: "",
    )

    await loop.run(
        Session(
            id="s1",
            workspace=".",
            provider="old-provider",
            model="old-session-model",
        ),
        "task",
    )

    assert provider.calls[0].model == "current-provider-model"


@pytest.mark.asyncio
async def test_loop_uses_global_model_when_session_same_provider_has_old_model():
    registry = ToolRegistry()
    registry.register(FinalTool())
    providers = ProviderRegistry()
    provider = MockProvider(responses=["DONE"])
    provider.model = "provider-model"
    providers.register("p", provider)
    loop = AgentLoop(
        provider=MockProvider(responses=["DONE"]),
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=2),
        provider_registry=providers,
        default_provider=lambda: "p",
        default_model=lambda: "global-model",
    )

    await loop.run(
        Session(
            id="s1",
            workspace=".",
            provider="p",
            model="old-session-model",
        ),
        "task",
    )

    assert provider.calls[0].model == "global-model"


@pytest.mark.asyncio
async def test_loop_injects_resolved_model_into_system_message_and_tracks_switch():
    registry = ToolRegistry()
    registry.register(FinalTool())
    providers = ProviderRegistry()
    provider = MockProvider(responses=["DONE", "DONE"])
    provider.model = "provider-model"
    providers.register("p", provider)
    state = {"model": "model-a"}
    loop = AgentLoop(
        provider=MockProvider(responses=["DONE"]),
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=2),
        provider_registry=providers,
        default_provider=lambda: "p",
        default_model=lambda: state["model"],
    )

    await loop.run(
        Session(id="s1", workspace=".", provider="p", model="old-session-model"),
        "task",
    )
    first_system = [
        message
        for message in provider.calls[0].messages
        if message.get("role") == "system"
    ]
    assert any("provider=p" in message["content"] for message in first_system)
    assert any("model=model-a" in message["content"] for message in first_system)

    state["model"] = "model-b"
    await loop.run(
        Session(id="s2", workspace=".", provider="p", model="old-session-model"),
        "task",
    )
    second_system = [
        message
        for message in provider.calls[1].messages
        if message.get("role") == "system"
    ]
    assert any("model=model-b" in message["content"] for message in second_system)


@pytest.mark.asyncio
async def test_loop_falls_back_to_injected_provider_when_registry_misses():
    registry = ToolRegistry()
    registry.register(FinalTool())
    fallback = MockProvider(responses=['{"tool":"final","args":{}}', "DONE"])
    loop = AgentLoop(
        provider=fallback,
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=3),
        provider_registry=ProviderRegistry(),  # 默认只含 mock，无 "missing"
        default_provider=lambda: "missing",
        default_model=lambda: "",
    )

    await loop.run(Session(id="s1", workspace="."), "task")

    assert len(fallback.calls) == 2


@pytest.mark.asyncio
async def test_loop_accepts_done_with_final_answer():
    registry = ToolRegistry()
    registry.register(FinalTool())
    provider = MockProvider(responses=["DONE: 我完成了任务"])
    loop = AgentLoop(
        provider=provider,
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=2),
    )

    result = await loop.run(Session(id="s1", workspace="."), "task")

    assert result == "DONE: 我完成了任务"
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_loop_emits_agent_message_before_tool_action(tmp_path):
    registry = ToolRegistry()
    registry.register(FinalTool())
    provider = MockProvider(responses=['先看一下目录结构\n{"tool":"final","args":{}}', "DONE"])
    logger = EventLogger(tmp_path / "audit.jsonl")
    loop = AgentLoop(
        provider=provider,
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=3),
        logger=logger,
    )

    await loop.run(Session(id="s1", workspace="."), "task")

    records = [
        json.loads(line)
        for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    ]
    assert any(record["event"] == "agent_message" for record in records)
    message = next(r for r in records if r["event"] == "agent_message")
    assert message["payload"]["text"] == "先看一下目录结构"
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_loop_tool_result_event_includes_args_and_output(tmp_path):
    """tool_result 事件带动作参数和输出摘要，供 TUI 显示命令与结果。"""
    registry = ToolRegistry()
    registry.register(FinalTool())
    provider = MockProvider(responses=['{"tool":"final","args":{"path":"a.ts"}}', "DONE"])
    logger = EventLogger(tmp_path / "audit.jsonl")
    loop = AgentLoop(
        provider=provider,
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=3),
        logger=logger,
    )

    await loop.run(Session(id="s1", workspace="."), "task")

    records = [
        json.loads(line)
        for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    ]
    tool_result = next(r for r in records if r["event"] == "tool_result")
    assert tool_result["payload"]["args"] == {"path": "a.ts"}
    assert tool_result["payload"]["output"] == "done"


@pytest.mark.asyncio
async def test_approved_action_logs_final_tool_result(tmp_path):
    """审批通过后补发一条最终 tool_result，工具结果对前端可见。"""
    executor, guardrail = make_approval_executor(tmp_path)
    provider = MockProvider(
        responses=[
            '{"tool":"run_command","args":{"command":"git push --force"}}',
            "DONE",
        ]
    )
    logger = EventLogger(tmp_path / "audit.jsonl")

    async def approve(task_id: str, action: dict) -> str:
        guardrail.hitl.approve(action["action_id"])
        return "approve"

    loop = AgentLoop(
        provider=provider,
        tools=executor,
        settings=LoopSettings(max_iterations=5),
        logger=logger,
        on_approval=approve,
    )

    result = await loop.run(Session(id="s1", workspace=str(tmp_path)), "deploy")

    assert result == "DONE"
    records = [
        json.loads(line)
        for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    ]
    results = [r for r in records if r["event"] == "tool_result"]
    assert len(results) == 2
    assert results[0]["payload"]["error"] == "requires_approval"
    assert results[1]["payload"]["ok"] is True
    assert results[1]["payload"]["output"] == '{"exit_code": 0, "stdout": "ok", "stderr": ""}'


@pytest.mark.asyncio
async def test_loop_parses_action_when_message_contains_braces(tmp_path):
    registry = ToolRegistry()
    registry.register(FinalTool())
    provider = MockProvider(
        responses=['先检查 {project} 目录\n{"tool":"final","args":{}}', "DONE"]
    )
    logger = EventLogger(tmp_path / "audit.jsonl")
    loop = AgentLoop(
        provider=provider,
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=3),
        logger=logger,
    )

    result = await loop.run(Session(id="s1", workspace="."), "task")

    assert result == "DONE"
    records = [
        json.loads(line)
        for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    ]
    message = next(r for r in records if r["event"] == "agent_message")
    assert message["payload"]["text"] == "先检查 {project} 目录"
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_loop_skips_noise_agent_message_for_native_tool_call(tmp_path):
    """原生 tool_calls 的 content 只有 `<` 时，不把噪声发给 TUI。"""
    registry = ToolRegistry()
    registry.register(FinalTool())

    class NoiseNativeProvider:
        async def complete(self, request):
            return ProviderResponse(
                text="<",
                tool_calls=[ProviderToolCall(id="c1", name="final", arguments="{}")],
            )

    logger = EventLogger(tmp_path / "audit.jsonl")
    loop = AgentLoop(
        provider=NoiseNativeProvider(),
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=3),
        logger=logger,
    )

    await loop.run(Session(id="s1", workspace="."), "task")

    records = [
        json.loads(line)
        for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    ]
    assert not any(record["event"] == "agent_message" for record in records)
