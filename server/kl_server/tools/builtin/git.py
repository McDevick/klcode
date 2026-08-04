import asyncio
import subprocess
from pathlib import Path
from typing import Any

from kl_server.models.action import ToolResult
from kl_server.tools.base import Tool, ToolContext


async def _git(workspace: str, *args: str) -> str:
    proc = await asyncio.to_thread(
        subprocess.run,
        ["git", *args],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip())
    return proc.stdout.strip()


class GitStatusTool(Tool):
    name = "git_status"
    description = "Show git status"
    schema = {"type": "object", "properties": {}}

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            return ToolResult(ok=True, output=await _git(ctx.workspace, "status"))
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            return ToolResult(ok=False, output="", error=str(exc))


class GitDiffTool(Tool):
    name = "git_diff"
    description = "Show working-tree diff"
    schema = {"type": "object", "properties": {}}

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            return ToolResult(ok=True, output=await _git(ctx.workspace, "diff"))
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            return ToolResult(ok=False, output="", error=str(exc))


class GitBranchTool(Tool):
    name = "git_branch"
    description = "Create and switch to a branch"
    schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            return ToolResult(ok=True, output=await _git(ctx.workspace, "switch", "-c", args["name"]))
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            return ToolResult(ok=False, output="", error=str(exc))


class GitCommitTool(Tool):
    name = "git_commit"
    description = "Stage explicit paths and create a commit"
    schema = {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "paths": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["message", "paths"],
    }

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        paths = args.get("paths")
        if not isinstance(paths, list) or not paths:
            return ToolResult(ok=False, output="", error="paths are required")
        root = Path(ctx.workspace).resolve()
        for path in paths:
            if not isinstance(path, str) or not path:
                return ToolResult(ok=False, output="", error="paths are required")
            if path.startswith(":"):
                return ToolResult(ok=False, output="", error="pathspec magic is not allowed")
            try:
                resolved = (root / path).resolve()
            except (OSError, ValueError):
                return ToolResult(ok=False, output="", error="invalid path")
            if not resolved.is_relative_to(root):
                return ToolResult(ok=False, output="", error="path outside workspace")
        try:
            await _git(ctx.workspace, "--literal-pathspecs", "add", "--", *paths)
            return ToolResult(
                ok=True,
                output=await _git(
                    ctx.workspace,
                    "--literal-pathspecs",
                    "commit",
                    "--only",
                    "-m",
                    args["message"],
                    "--",
                    *paths,
                ),
            )
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            return ToolResult(ok=False, output="", error=str(exc))
