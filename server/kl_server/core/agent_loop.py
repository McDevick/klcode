import json
from dataclasses import dataclass

from kl_server.models.action import Action
from kl_server.models.task import Session
from kl_server.providers.base import ProviderRequest
from kl_server.tools.base import ToolContext
from kl_server.tools.registry import ToolRegistry


@dataclass
class LoopSettings:
    max_iterations: int = 10


class AgentLoop:
    def __init__(self, provider, tools: ToolRegistry, settings: LoopSettings):
        self.provider = provider
        self.tools = tools
        self.settings = settings

    async def run(self, session: Session, task: str) -> str:
        history = [{"role": "user", "content": task}]
        for _ in range(self.settings.max_iterations):
            response = await self.provider.complete(ProviderRequest(messages=history, model=session.model))
            text = response.text.strip()
            if text == "DONE":
                return text
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                history.append({"role": "assistant", "content": text})
                continue
            result = await self.tools.execute(
                payload["tool"],
                payload.get("args", {}),
                ToolContext(workspace=session.workspace),
            )
            history.append({"role": "assistant", "content": text})
            history.append({"role": "tool", "content": result.output})
        return "MAX_ITERATIONS"
