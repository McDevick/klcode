import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, replace

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
    retry_budget: int = 3


# Native tool calling: the provider receives the tool catalog via the OpenAI
# `tools` request parameter, so this prompt only needs to steer behavior —
# not teach the JSON action protocol. A response without tool_calls IS the
# final answer.
SYSTEM_PROMPT = """你是运行在本地工作区中的自主编码 Agent。
你的目标是可靠地完成用户任务，而不是假装完成。

## 工具使用原则

1. 获取信息时，先用 grep/glob 定位，再精确读取。
2. 大文件不要一次读完整内容；优先使用 read_file(start_line, end_line)。
3. 小范围修改优先使用 edit_file，而不是 write_file 重写整个文件。
4. 只有创建新文件或必须整文件覆盖时才使用 write_file。
5. 每个工具调用只做一件明确的事，避免一次执行大量无关操作。

## 任务计划

1. 多步骤任务开始前，先调用 task_manage(list) 查看当前 session 是否已有计划。
2. 没有计划时创建；有计划时不要重复创建相同任务。
3. 每完成一步，立即调用 task_manage(update) 更新状态。
4. 计划状态在同一 session 内共享，后续任务可以读取和继续。

## 审批

1. 工具返回 requires_approval 时，停止当前操作，等待用户批准、拒绝或中止。
2. 不要绕过审批，不要重复提交等待审批的同一个操作。
3. 如果用户拒绝，换一种可行方案，而不是原样重试。

## 意外情况处理

1. 工具调用失败时，先读取 error 信息，判断是参数错误、路径错误、权限错误、编码错误还是环境问题。
2. 如果错误明确，修正参数或改用更合适的工具，最多尝试 2-3 次。
3. 如果同一个工具连续失败，停止重复尝试，换工具、换思路，或向用户报告卡点。
4. 如果命令返回非零退出码，不要忽略；根据 stdout/stderr 判断是否可修复。
5. 如果工具输出被截断，说明内容过长；使用范围读取、缩小搜索范围或分步处理。
6. 如果文件不存在，不要编造内容；确认路径或让用户提供正确路径。
7. 如果权限不足、文件被占用或编码不支持，如实报告，不要强行修改。
8. 如果遇到 provider/API/网络错误，检查是否是临时故障；若不能确认，不要重复轰炸接口。
9. 如果用户要求访问 workspace 外路径，不执行绕过操作；说明限制，并建议复制文件到 workspace 内。
10. 如果结果不确定，明确说“不确定”，并说明缺少哪些证据。
11. 如果任务无法完成，不要输出成功；说明已做了什么、卡在哪里、需要用户提供什么。
12. 任何时候都不要编造工具结果、文件内容、测试结果或提交记录。

## 验证

1. 修改代码后，运行相关测试、lint 或 typecheck。
2. 能验证就给出验证结果；不能验证就明确说明“未验证”。
3. 验证失败时，先修复，再重新验证，不要直接宣告完成。

## 最终回答

1. 使用与用户相同的语言回复。
2. 简洁说明：
   - 你做了什么
   - 改了什么文件
   - 如何验证
   - 是否还有未完成或不确定的部分
3. 如果任务完成，给出关键结果；如果未完成，给出下一步建议。
"""


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
        self._instructions: dict[str, list[str]] = {}

    def set_paused(self, task_id: str, paused: bool) -> None:
        """Pause (clear gate) or resume (remove gate) a task's execution."""
        if paused:
            self._pause_events.setdefault(task_id, asyncio.Event()).clear()
            return
        event = self._pause_events.pop(task_id, None)
        if event is not None:
            event.set()

    def add_instruction(self, task_id: str, instruction: str) -> None:
        self._instructions.setdefault(task_id, []).append(instruction)

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
        category_streak: dict[str, int] = {}
        budget_warned: set[str] = set()
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
            pending_instructions = self._instructions.pop(task_id, [])
            for instruction in pending_instructions:
                history.append(
                    {
                        "role": "user",
                        "content": f"[追加说明] {instruction}",
                    }
                )
                if self.logger:
                    self.logger.write(
                        "instruction_added",
                        {"instruction": instruction[:500]},
                        task_id,
                    )
            if self.logger:
                self.logger.write("llm_call", {"iteration": iteration}, task_id)
            try:
                history_texts = [
                    f"{message['role']}: {message.get('content', '')}"
                    for message in history
                ]
                context_summary = ""
                recent_history = history
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
                    should_compress = getattr(self.context, "should_compress", None)
                    compact_history = getattr(self.context, "compact_history", None)
                    if should_compress is not None and should_compress(history_texts):
                        try:
                            if compact_history is not None:
                                context_summary = await compact_history(
                                    history_texts,
                                    task_id,
                                )
                        except Exception:
                            context_summary = ""
                        if context_summary:
                            recent_history = history[-4:]
                            history = recent_history
                            if self.memory is not None:
                                try:
                                    await self.memory.add(
                                        session.id,
                                        "context_summary",
                                        [session.id],
                                        context_summary[:5000],
                                    )
                                except Exception:
                                    pass
                request_messages = [system_message]
                if self.context is not None:
                    if assembled.text:
                        request_messages.append(
                            {"role": "system", "content": assembled.text}
                        )
                    if context_summary:
                        request_messages.append(
                            {
                                "role": "system",
                                "content": f"Previous context summary:\n{context_summary}",
                            }
                        )
                request_messages.extend(recent_history)
                provider = self.provider
                if self.provider_registry is not None and self.default_provider is not None:
                    try:
                        provider = self.provider_registry.get(self.default_provider())
                    except KeyError:
                        pass  # 回退 self.provider
                # Sessions default to the mock model name; fall back to the
                # global default model, then to the provider's own default.
                resolved_provider_name = (
                    self.default_provider()
                    if self.default_provider is not None
                    else ""
                )
                provider_mismatch = bool(
                    resolved_provider_name
                    and session.provider
                    and session.provider.lower() != resolved_provider_name.lower()
                )
                global_model = (
                    self.default_model() if self.default_model is not None else ""
                ) or ""
                model = session.model
                if global_model:
                    model = global_model
                elif not model or model == "mock-model" or provider_mismatch:
                    model = getattr(provider, "model", None) or model
                request_messages.insert(
                    1,
                    {
                        "role": "system",
                        "content": (
                            "当前运行模型: "
                            f"provider={resolved_provider_name or 'default'}, "
                            f"model={model}"
                        ),
                    },
                )
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
                    self.logger.write(
                        "feedback_generation",
                        {
                            "tool": "provider",
                            "category": "provider_error",
                            "summary": str(exc)[:300],
                        },
                        task_id,
                    )
                if self.hooks:
                    self.hooks.run(
                        "error",
                        {"reason": "provider_error", "error": str(exc)[:500]},
                    )
                    self.hooks.run("task_end", {"reason": "provider_error"})
                if self.memory is not None:
                    try:
                        await self.memory.add(
                            session.id,
                            "feedback",
                            [session.id, task_id],
                            f"provider: provider_error: {str(exc)[:400]}",
                        )
                    except Exception:
                        pass
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
                    ToolContext(
                        workspace=session.workspace,
                        task_id=session.id,
                        session_id=session.id,
                        workspace_mode=workspace_mode,
                        state_store=self.memory,
                    ),
                )
                if self.logger:
                    event_output = result.summary or result.output
                    if result.truncated and result.references:
                        event_output += (
                            "\n[文件引用] " + ", ".join(result.references)
                        )
                    self.logger.write(
                        "tool_result",
                        {
                            "tool": action.tool,
                            "ok": result.ok,
                            "error": result.error,
                            "meta": result.meta,
                            "args": action.args,
                            "output": event_output[:500],
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
                            session_id=session.id,
                            workspace_mode=workspace_mode,
                            state_store=self.memory,
                        ),
                        action_id,
                    )
                    # 审批通过后补发一条最终结果事件，工具树才能看到真实结果
                    if self.logger:
                        event_output = result.summary or result.output
                        if result.truncated and result.references:
                            event_output += (
                                "\n[文件引用] " + ", ".join(result.references)
                            )
                        self.logger.write(
                            "tool_result",
                            {
                                "tool": action.tool,
                                "ok": result.ok,
                                "error": result.error,
                                "meta": result.meta,
                                "args": action.args,
                                "output": event_output[:500],
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
                feedback = replace(
                    classify_tool_result(result, action.tool),
                    raw_ref=f"{task_id}:{call.id}",
                )
                feedback_text = f"{feedback.category.value}: {feedback.summary[-500:]}"
                if not feedbacks or feedbacks[-1] != feedback_text:
                    feedbacks.append(feedback_text)
                category = feedback.category.value
                if category == "success":
                    category_streak.clear()
                else:
                    streak = category_streak.get(category, 0) + 1
                    category_streak[category] = streak
                    if (
                        self.settings.retry_budget > 0
                        and streak >= self.settings.retry_budget
                        and category not in budget_warned
                    ):
                        budget_warned.add(category)
                        feedbacks.append(
                            "retry_budget_exhausted: "
                            f"{category} repeated {streak} times; "
                            "stop repeating the same approach and reassess"
                        )
                if self.logger:
                    self.logger.write(
                        "feedback_generation",
                        {
                            "tool": action.tool,
                            "category": feedback.category.value,
                            "summary": feedback.summary[:300],
                        },
                        task_id,
                    )
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
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": (
                            (result.summary if result.summary is not None else result.output)
                            + (
                                "\n[文件引用] " + ", ".join(result.references)
                                if result.truncated and result.references
                                else ""
                            )
                        ),
                    }
                )
                if self.memory is not None:
                    try:
                        await self.memory.add(
                            session.id,
                            "tool_result",
                            [session.id, task_id],
                            f"{action.tool}: {feedback.summary[-400:]}",
                        )
                        await self.memory.add(
                            session.id,
                            "feedback",
                            [session.id, task_id],
                            f"{action.tool}: {feedback.category.value}: {feedback.summary[-400:]}",
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
