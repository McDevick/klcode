from dataclasses import dataclass, field
from typing import Any, Protocol

from kl_server.models.action import ToolResult


@dataclass
class ToolContext:
    workspace: str
    task_id: str = ""
    session_id: str | None = None
    workspace_mode: str = "managed"
    task_state: dict = field(default_factory=dict)
    state_store: object | None = None


class Tool(Protocol):
    name: str
    description: str
    schema: dict[str, Any]

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        ...
