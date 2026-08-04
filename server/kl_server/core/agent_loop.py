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

    async def run(self, session: Session, task: str, task_id: str = "") -> str:
        history = [{"role": "user", "content": task}]
        if self.logger:
            self.logger.write("loop_start", {"task": task[:500]}, task_id)
        for _ in range(self.settings.max_iterations):
            if self.logger:
                self.logger.write("llm_call", {"iteration": _}, task_id)
            response = await self.provider.complete(ProviderRequest(messages=history, model=session.model))
            text = response.text.strip()
            if text == "DONE":
                if self.logger:
                    self.logger.write("loop_end", {"reason": "done"}, task_id)
                return text
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                history.append({"role": "assistant", "content": text})
                history.append(
                    {
                        "role": "feedback",
                        "content": "provider_error: invalid action; expected JSON object",
                    }
                )
                continue
            if not self._is_valid_action(payload):
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
                ToolContext(workspace=session.workspace, task_id=session.id),
            )
            if self.logger:
                self.logger.write(
                    "tool_result",
                    {"tool": action.tool, "ok": result.ok, "error": result.error},
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
