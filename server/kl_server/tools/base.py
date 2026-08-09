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
    permissions: list[str] = field(default_factory=list)
    sandbox: dict[str, Any] = field(default_factory=dict)
    tool_timeout: float | None = None
    tool_outputs_dir: str | None = None


class Tool(Protocol):
    name: str
    description: str
    schema: dict[str, Any]
    permissions: list[str]
    sandbox: dict[str, Any]
    timeout: float | None

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        ...
