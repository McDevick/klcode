import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass

from kl_server.core.feedback import classify_tool_result
from kl_server.core.tool_executor import ToolExecutor
from kl_server.models.action import Action
from kl_server.models.task import Session
from kl_server.providers.base import ProviderRequest
from kl_server.providers.registry import ProviderRegistry
from kl_server.tools.base import ToolContext


@dataclass
class LoopSettings:
    max_iterations: int = 10


# Instructs a real (non-mock) LLM about the action protocol the loop drives.
# The agent loop only accepts "DONE[: <answer>]" or a JSON action object;
# without this prompt a real model replies with free text and the loop
# bounces it back as invalid_action until max_iterations.
SYSTEM_PROMPT = (
    "You are an autonomous coding agent operating in a local workspace. "
    "You accomplish the task by calling tools from the tool catalog listed "
    "in the context message below.\n"
    "RESPONSE FORMAT (strict):\n"
    "- To take an action, reply with a JSON object of the form "
    '{"tool": "<tool_name>", "args": {<argument name>: <value>, ...}}.\n'
    "  You may optionally prefix it with a short message to the user "
    '(e.g. "Let me check the directory first."), then the JSON on its own line.\n'
    "- When the task is fully complete, reply with DONE, optionally followed "
    "by your final answer to the user: DONE: <your answer>.\n"
    "Any other free text is treated as an error and sent back to you. "
    "Use one of the two formats above, nothing else."
)


def _split_message_and_json(text: str) -> tuple[str, str]:
    """把模型回复拆成可选的用户消息前缀和 JSON 动作。

    模型可能在 JSON 动作前附带简短消息（消息本身可能含有花括号，例如
    "先检查 {project} 目录"），因此从末尾往前扫描 "{" 候选起点，取第一个
    能完整解析为 JSON 的片段，其前内容作为消息。
    """
    stripped = text.strip()
    if not stripped:
        return "", text
    close = stripped.rfind("}")
    start = stripped.rfind("{", 0, close) if close >= 0 else -1
    while start >= 0:
        candidate = stripped[start : close + 1]
        try:
            json.loads(candidate)
        except json.JSONDecodeError:
            start = stripped.rfind("{", 0, start)
            continue
        return stripped[:start].strip(), candidate
    return "", text


class AgentLoop:
    def __init__(
        self,
        provider,
        tools: ToolExecutor,
        settings: LoopSettings,
        logger=None,
        on_approval=None,
        context=None,
        memory=None,
        hooks=None,
        skills=None,
        provider_registry: ProviderRegistry | None = None,
        default_provider: Callable[[], str] | None = None,
        default_model: Callable[[], str] | None = None,
    ):
        self.provider = provider
        self.provider_registry = provider_registry
        self.default_provider = default_provider
        self.default_model = default_model
        self.tools = tools
        self.settings = settings
        self.logger = logger
        self.on_approval = on_approval
        self.context = context
        self.memory = memory
        self.hooks = hooks
        self.skills = skills
        # task_id -> gate event；pause 时 clear，resume/重新 run 时移除并 set。
        # AgentLoop 在迭代边界 await，使 /pause 真正挂起执行而非只改数据库状态。
        self._pause_events: dict[str, asyncio.Event] = {}

    def set_paused(self, task_id: str, paused: bool) -> None:
        """Pause (clear gate) or resume (remove gate) a task's execution."""
        if paused:
            self._pause_events.setdefault(task_id, asyncio.Event()).clear()
            return
        event = self._pause_events.pop(task_id, None)
        if event is not None:
            event.set()

    async def _wait_if_paused(self, task_id: str) -> None:
        """Block until the task is resumed (no-op when not paused)."""
        event = self._pause_events.get(task_id)
        if event is not None:
            await event.wait()

    async def run(self, session: Session, task: str, task_id: str = "", workspace_mode: str = "managed") -> str:
        task_id = task_id or session.id
        history = [{"role": "user", "content": task}]
        if self.logger:
            self.logger.write("loop_start", {"task": task[:500]}, task_id)
        if self.hooks:
            self.hooks.run("task_start", {"task": task[:500]})
        if self.memory is not None:
            try:
                await self.memory.add(session.id, "task", [session.id, task_id], task[:500])
            except Exception:
                if self.logger:
                    self.logger.write("memory_error", {"kind": "task"}, task_id)
        system_message = {"role": "system", "content": SYSTEM_PROMPT}
        for iteration in range(self.settings.max_iterations):
            await self._wait_if_paused(task_id)
            if self.logger:
                self.logger.write("llm_call", {"iteration": iteration}, task_id)
            try:
                request_messages = [system_message, *history]
                if self.context is not None:
                    memory_entries = (
                        await self.memory.find([session.id, task_id])
                        if self.memory is not None
                        else []
                    )
                    assembled = await self.context.build(
                        tool_catalog=(
                            self.tools.catalog()
                            if hasattr(self.tools, "catalog")
                            else []
                        ),
                        rules=getattr(session, "rules", ""),
                        memory=memory_entries,
                        history=[
                            f"{message['role']}: {message['content']}"
                            for message in history
                        ],
                        task_id=task_id,
                        skills=(
                            self.skills.load([task])
                            if self.skills is not None
                            else ""
                        ),
                    )
                    request_messages = [
                        system_message,
                        {"role": "user", "content": assembled.text},
                    ]
                provider = self.provider
                if self.provider_registry is not None and self.default_provider is not None:
                    try:
                        provider = self.provider_registry.get(self.default_provider())
                    except KeyError:
                        pass  # 回退 self.provider
                # Sessions default to the mock model name; fall back to the
                # global default model, then to the provider's own default.
                model = session.model
                if not model or model == "mock-model":
                    global_model = (self.default_model() if self.default_model is not None else "") or ""
                    model = global_model or (getattr(provider, "model", None) or model)
                response = await provider.complete(
                    ProviderRequest(messages=request_messages, model=model)
                )
            except Exception as exc:
                if self.logger:
                    self.logger.write("provider_error", {"error": str(exc)[:500]}, task_id)
                    self.logger.write("loop_end", {"reason": "provider_error"}, task_id)
                if self.hooks:
                    self.hooks.run(
                        "error",
                        {"reason": "provider_error", "error": str(exc)[:500]},
                    )
                    self.hooks.run("task_end", {"reason": "provider_error"})
                raise
            # provider 调用期间可能收到 /pause；在消费结果前再等一次门控，
            # 保证暂停中的任务不会越过 DONE/动作处理而“偷偷完成”。
            await self._wait_if_paused(task_id)
            text = response.text.strip()
            if self.logger:
                self.logger.write("llm_result", {"text": text[:500]}, task_id)
            if text == "DONE" or text.startswith("DONE:"):
                if self.logger:
                    self.logger.write("loop_end", {"reason": "done"}, task_id)
                if self.hooks:
                    self.hooks.run("task_end", {"reason": "done"})
                return text
            # 允许模型在 JSON 动作前附带给用户的消息（如"我先看一下目录结构"），
            # 消息部分以 agent_message 事件实时推送给前端。
            message, json_text = _split_message_and_json(text)
            if message and self.logger:
                self.logger.write("agent_message", {"text": message[:500]}, task_id)
            try:
                payload = json.loads(json_text)
            except json.JSONDecodeError:
                if self.logger:
                    self.logger.write("invalid_action", {"reason": "not-json", "text": text[:500]}, task_id)
                history.append({"role": "assistant", "content": text})
                history.append(
                    {
                        "role": "feedback",
                        "content": "invalid_action: expected JSON object",
                    }
                )
                continue
            if not self._is_valid_action(payload):
                if self.logger:
                    self.logger.write("invalid_action", {"reason": "invalid-schema", "text": text[:500]}, task_id)
                history.append({"role": "assistant", "content": text})
                history.append(
                    {
                        "role": "feedback",
                        "content": 'invalid_action: expected {"tool": str, "args": dict}',
                    }
                )
                continue
            action = Action(
                tool=payload["tool"],
                args=payload["args"],
                task_id=session.id,
                workspace=session.workspace,
            )
            if self.hooks:
                self.hooks.run(
                    "action_before",
                    {"tool": action.tool, "args": action.args},
                )
            result = await self.tools.execute(
                action.tool,
                action.args,
                ToolContext(workspace=session.workspace, task_id=session.id, workspace_mode=workspace_mode),
            )
            if self.logger:
                self.logger.write(
                    "tool_result",
                    {"tool": action.tool, "ok": result.ok, "error": result.error, "meta": result.meta},
                    task_id,
                )
            if result.error == "requires_approval":
                action_id = result.meta.get("action_id") or f"{task_id}:{action.tool}"
                if self.hooks:
                    self.hooks.run(
                        "approval_request",
                        {
                            "action_id": action_id,
                            "tool": action.tool,
                            "args": action.args,
                        },
                    )
                if self.on_approval is None:
                    if self.logger:
                        self.logger.write("loop_end", {"reason": "needs_approval"}, task_id)
                    if self.hooks:
                        self.hooks.run("task_end", {"reason": "needs_approval"})
                    return "NEEDS_APPROVAL"
                decision = await self.on_approval(
                    task_id or session.id,
                    {
                        "action_id": action_id,
                        "tool": action.tool,
                        "args": action.args,
                        "level": result.meta.get("level", ""),
                    },
                )
                if self.hooks:
                    self.hooks.run(
                        "approval_complete",
                        {"action_id": action_id, "decision": decision},
                    )
                if decision == "reject":
                    history.append({"role": "assistant", "content": text})
                    history.append({"role": "feedback", "content": "action rejected by user"})
                    continue
                if decision == "abort":
                    if self.hooks:
                        self.hooks.run("abort", {"action_id": action_id})
                    if self.logger:
                        self.logger.write("loop_end", {"reason": "aborted"}, task_id)
                    if self.hooks:
                        self.hooks.run("task_end", {"reason": "aborted"})
                    return "ABORTED"
                if decision != "approve":
                    history.append({"role": "assistant", "content": text})
                    history.append(
                        {"role": "feedback", "content": f"unknown approval decision: {decision}"}
                    )
                    continue
                result = await self.tools.execute_approved(
                    action.tool,
                    action.args,
                    ToolContext(
                        workspace=session.workspace,
                        task_id=session.id,
                        workspace_mode=workspace_mode,
                    ),
                    action_id,
                )
            if self.hooks:
                self.hooks.run(
                    "tool_after",
                    {"tool": action.tool, "ok": result.ok},
                )
                if result.error and result.error != "requires_approval":
                    self.hooks.run(
                        "error",
                        {"tool": action.tool, "error": result.error},
                    )
            feedback = classify_tool_result(result, action.tool)
            if self.hooks:
                self.hooks.run(
                    "feedback_generation",
                    {
                        "tool": action.tool,
                        "category": feedback.category.value,
                    },
                )
            history.append({"role": "assistant", "content": text})
            history.append({"role": "tool", "content": result.output})
            history.append({"role": "feedback", "content": f"{feedback.category.value}: {feedback.summary[-500:]}"})
            if self.memory is not None:
                try:
                    await self.memory.add(
                        session.id,
                        "tool_result",
                        [session.id, task_id],
                        f"{action.tool}: {feedback.summary[:400]}",
                    )
                except Exception:
                    if self.logger:
                        self.logger.write(
                            "memory_error",
                            {"kind": "tool_result", "tool": action.tool},
                            task_id,
                        )
        if self.logger:
            self.logger.write("loop_end", {"reason": "max_iterations"}, task_id)
        if self.hooks:
            self.hooks.run("task_end", {"reason": "max_iterations"})
        return "MAX_ITERATIONS"

    @staticmethod
    def _is_valid_action(payload: object) -> bool:
        return (
            isinstance(payload, dict)
            and isinstance(payload.get("tool"), str)
            and isinstance(payload.get("args"), dict)
        )
