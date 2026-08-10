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
    permissions: list[str] = field(default_factory=list)
    sandbox: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    ok: bool
    output: str
    error: str | None = None
    meta: dict = field(default_factory=dict)
    summary: str | None = None
    truncated: bool = False
    references: list[str] = field(default_factory=list)
