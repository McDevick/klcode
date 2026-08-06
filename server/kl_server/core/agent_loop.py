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


# Native tool calling: the provider receives the tool catalog via the OpenAI
# `tools` request parameter, so this prompt only needs to steer behavior —
# not teach the JSON action protocol. A response without tool_calls IS the
# final answer.
SYSTEM_PROMPT = (
    "You are an autonomous coding agent operating in the local workspace. "
    "Use the provided tools to complete the user's task, one tool call at a "
    "time. Some actions require user approval; if one is rejected, take a "
    "different approach instead of repeating it. When the task is complete, "
    "reply with your final answer to the user. "
    "Reply in the same language as the user's task."
)


def _clean_user_message(text: str) -> str:
    """去掉模型在工具调用前输出的 `<`/`>` 等纯噪声标记。"""
    cleaned = text.strip()
    while cleaned and cleaned[0] in "<>|~":
        cleaned = cleaned[1:].lstrip()
    while cleaned and cleaned[-1] in "<>|~":
        cleaned = cleaned[:-1].rstrip()
    return cleaned.strip()


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

    def _tools_spec(self) -> list[dict] | None:
        """Build the OpenAI `tools` request parameter from the tool catalog."""
        if not hasattr(self.tools, "catalog"):
            return None
        catalog = self.tools.catalog()
        if not catalog:
            return None
        specs = []
        for tool in catalog:
            schema = tool.get("schema") or {}
            specs.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.get("name", ""),
                        "description": tool.get("description", ""),
                        "parameters": schema,
                    },
                }
            )
        return specs

    async def run(self, session: Session, task: str, task_id: str = "", workspace_mode: str = "managed") -> str:
        task_id = task_id or session.id
        history: list[dict] = [{"role": "user", "content": task}]
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
                request_messages = [system_message]
                if self.context is not None:
                    memory_entries = (
                        await self.memory.find([session.id, task_id])
                        if self.memory is not None
                        else []
                    )
                    assembled = await self.context.build(
                        rules=getattr(session, "rules", ""),
                        memory=memory_entries,
                        history=[],
                        task_id=task_id,
                        skills=(
                            self.skills.load([task])
                            if self.skills is not None
                            else ""
                        ),
                    )
                    if assembled.text:
                        request_messages.append(
                            {"role": "system", "content": assembled.text}
                        )
                request_messages.extend(history)
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
                    ProviderRequest(
                        messages=request_messages,
                        model=model,
                        tools=self._tools_spec(),
                    )
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
            # 保证暂停中的任务不会越过结果处理而"偷偷完成"。
            await self._wait_if_paused(task_id)
            text = (response.text or "").strip()
            tool_calls = response.tool_calls or []
            if self.logger:
                payload: dict = {}
                if text:
                    payload["text"] = text[:500]
                if tool_calls:
                    payload["tool_calls"] = [
                        {"name": call.name, "arguments": call.arguments[:200]}
                        for call in tool_calls
                    ]
                self.logger.write("llm_result", payload, task_id)
            if not tool_calls:
                # 无工具调用：模型直接给出最终回答（原生格式没有 DONE 标记）。
                if self.logger:
                    self.logger.write("loop_end", {"reason": "done"}, task_id)
                if self.hooks:
                    self.hooks.run("task_end", {"reason": "done"})
                return text or "DONE"
            if text:
                # 有工具调用时 content 是给用户的动作前消息
                if self.logger:
                    user_message = _clean_user_message(text)
                    if user_message:
                        self.logger.write("agent_message", {"text": user_message[:500]}, task_id)
            # assistant 消息必须携带本次的 tool_calls（OpenAI 格式要求：
            # 后续 tool 消息按 tool_call_id 关联）。
            history.append(
                {
                    "role": "assistant",
                    "content": _clean_user_message(text),
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": call.arguments,
                            },
                        }
                        for call in tool_calls
                    ],
                }
            )
            feedbacks: list[str] = []
            for call in tool_calls:
                name = call.name
                try:
                    args = json.loads(call.arguments) if call.arguments else {}
                except json.JSONDecodeError:
                    args = {}
                if not isinstance(args, dict):
                    args = {}
                action = Action(
                    tool=name,
                    args=args,
                    task_id=session.id,
                    seq=iteration,
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
                        {
                            "tool": action.tool,
                            "ok": result.ok,
                            "error": result.error,
                            "meta": result.meta,
                            "args": action.args,
                            "output": result.output[:500],
                        },
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
                    if decision == "abort":
                        if self.hooks:
                            self.hooks.run("abort", {"action_id": action_id})
                        if self.logger:
                            self.logger.write("loop_end", {"reason": "aborted"}, task_id)
                        if self.hooks:
                            self.hooks.run("task_end", {"reason": "aborted"})
                        return "ABORTED"
                    if decision == "reject":
                        # 该调用被拒绝：结果回传"拒绝"反馈，其余调用继续
                        history.append(
                            {"role": "tool", "tool_call_id": call.id, "content": "action rejected by user"}
                        )
                        continue
                    if decision != "approve":
                        history.append(
                            {"role": "tool", "tool_call_id": call.id, "content": f"unknown approval decision: {decision}"}
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
                    # 审批通过后补发一条最终结果事件，工具树才能看到真实结果
                    if self.logger:
                        self.logger.write(
                            "tool_result",
                            {
                                "tool": action.tool,
                                "ok": result.ok,
                                "error": result.error,
                                "meta": result.meta,
                                "args": action.args,
                                "output": result.output[:500],
                            },
                            task_id,
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
                feedbacks.append(f"{feedback.category.value}: {feedback.summary[-500:]}")
                if self.hooks:
                    self.hooks.run(
                        "feedback_generation",
                        {
                            "tool": action.tool,
                            "category": feedback.category.value,
                        },
                    )
                # 原生格式：工具结果按 tool_call_id 回传为 role: tool
                history.append(
                    {"role": "tool", "tool_call_id": call.id, "content": result.output}
                )
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
            if feedbacks:
                # 工具结果的分类反馈（成功/失败/超时等）注入为 user 消息
                history.append({"role": "user", "content": "feedback:\n" + "\n".join(feedbacks)})
        if self.logger:
            self.logger.write("loop_end", {"reason": "max_iterations"}, task_id)
        if self.hooks:
            self.hooks.run("task_end", {"reason": "max_iterations"})
        return "MAX_ITERATIONS"
