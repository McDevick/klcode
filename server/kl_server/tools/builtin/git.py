import subprocess
from typing import Any

from kl_server.models.action import ToolResult
from kl_server.tools.base import Tool, ToolContext


def _git(workspace: str, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=workspace, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip())
    return proc.stdout.strip()


class GitStatusTool(Tool):
    name = "git_status"
    description = "Show git status"
    schema = {"type": "object", "properties": {}}

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            return ToolResult(ok=True, output=_git(ctx.workspace, "status"))
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            return ToolResult(ok=False, output="", error=str(exc))


class GitDiffTool(Tool):
    name = "git_diff"
    description = "Show working-tree diff"
    schema = {"type": "object", "properties": {}}

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            return ToolResult(ok=True, output=_git(ctx.workspace, "diff"))
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            return ToolResult(ok=False, output="", error=str(exc))


class GitBranchTool(Tool):
    name = "git_branch"
    description = "Create and switch to a branch"
    schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            return ToolResult(ok=True, output=_git(ctx.workspace, "switch", "-c", args["name"]))
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            return ToolResult(ok=False, output="", error=str(exc))


class GitCommitTool(Tool):
    name = "git_commit"
    description = "Commit all current changes"
    schema = {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]}

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            _git(ctx.workspace, "add", "-A")
            return ToolResult(ok=True, output=_git(ctx.workspace, "commit", "-m", args["message"]))
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            return ToolResult(ok=False, output="", error=str(exc))
