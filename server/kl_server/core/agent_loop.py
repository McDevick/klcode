import json
from dataclasses import dataclass

from kl_server.core.feedback import classify_tool_result
from kl_server.core.tool_executor import ToolExecutor
from kl_server.models.action import Action
from kl_server.models.task import Session
from kl_server.providers.base import ProviderRequest
from kl_server.tools.base import ToolContext


@dataclass
class LoopSettings:
    max_iterations: int = 10


class AgentLoop:
    def __init__(self, provider, tools: ToolExecutor, settings: LoopSettings, logger=None):
        self.provider = provider
        self.tools = tools
        self.settings = settings
        self.logger = logger

    async def run(self, session: Session, task: str, task_id: str = "", workspace_mode: str = "managed") -> str:
        task_id = task_id or session.id
        history = [{"role": "user", "content": task}]
        if self.logger:
            self.logger.write("loop_start", {"task": task[:500]}, task_id)
        for iteration in range(self.settings.max_iterations):
            if self.logger:
                self.logger.write("llm_call", {"iteration": iteration}, task_id)
            try:
                response = await self.provider.complete(ProviderRequest(messages=history, model=session.model))
            except Exception as exc:
                if self.logger:
                    self.logger.write("provider_error", {"error": str(exc)[:500]}, task_id)
                    self.logger.write("loop_end", {"reason": "provider_error"}, task_id)
                raise
            text = response.text.strip()
            if self.logger:
                self.logger.write("llm_result", {"text": text[:500]}, task_id)
            if text == "DONE":
                if self.logger:
                    self.logger.write("loop_end", {"reason": "done"}, task_id)
                return text
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                if self.logger:
                    self.logger.write("invalid_action", {"reason": "not-json", "text": text[:500]}, task_id)
                history.append({"role": "assistant", "content": text})
                history.append(
                    {
                        "role": "feedback",
                        "content": "provider_error: invalid action; expected JSON object",
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
                        "content": 'provider_error: invalid action; expected {"tool": str, "args": dict}',
                    }
                )
                continue
            action = Action(
                tool=payload["tool"],
                args=payload["args"],
                task_id=session.id,
                workspace=session.workspace,
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
            feedback = classify_tool_result(result, action.tool)
            history.append({"role": "assistant", "content": text})
            history.append({"role": "tool", "content": result.output})
            history.append({"role": "feedback", "content": f"{feedback.category.value}: {feedback.summary[-500:]}"})
        if self.logger:
            self.logger.write("loop_end", {"reason": "max_iterations"}, task_id)
        return "MAX_ITERATIONS"

    @staticmethod
    def _is_valid_action(payload: object) -> bool:
        return (
            isinstance(payload, dict)
            and isinstance(payload.get("tool"), str)
            and isinstance(payload.get("args"), dict)
        )
