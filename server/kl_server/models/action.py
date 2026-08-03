from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Action:
    tool: str
    args: dict[str, Any]
    task_id: str
    seq: int = 0
    workspace: str = ""
    raw_command: str | None = None


@dataclass
class ToolResult:
    ok: bool
    output: str
    error: str | None = None
