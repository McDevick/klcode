import re
import os
from pathlib import Path, PurePath
from typing import Any

from kl_server.models.action import ToolResult
from kl_server.tools.base import Tool, ToolContext

_IGNORED_DIRS = {
    ".git",
    ".kl",
    ".claude",
    ".superpowers",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
}


def _is_ignored(path: Path) -> bool:
    return any(part in _IGNORED_DIRS for part in path.parts)


class GrepTool(Tool):
    name = "grep"
    description = "Search file contents by regex inside the workspace"
    schema = {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string", "default": "."}}, "required": ["pattern"]}

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        root = Path(ctx.workspace).resolve()
        search_root = (root / args.get("path", ".")).resolve()
        if not search_root.is_relative_to(root):
            return ToolResult(ok=False, output="", error="path outside workspace")
        try:
            pattern = re.compile(args["pattern"])
        except re.error as exc:
            return ToolResult(ok=False, output="", error=f"invalid regex: {exc}")
        matches = []
        for dirpath, dirnames, filenames in os.walk(search_root, onerror=lambda exc: None):
            dirnames[:] = [name for name in dirnames if name not in _IGNORED_DIRS]
            for filename in filenames:
                try:
                    resolved = (Path(dirpath) / filename).resolve()
                except OSError:
                    continue
                if (
                    _is_ignored(resolved)
                    or not resolved.is_relative_to(root)
                    or not resolved.is_file()
                ):
                    continue
                try:
                    text = resolved.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if pattern.search(text):
                    matches.append(str(resolved.relative_to(root)))
        return ToolResult(ok=True, output="\n".join(matches))


class GlobTool(Tool):
    name = "glob"
    description = "Find files matching a glob pattern inside the workspace"
    schema = {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        root = Path(ctx.workspace).resolve()
        pattern = args["pattern"].replace("\\", "/")
        if pattern.startswith("./"):
            pattern = pattern[2:]
        matches = []
        for dirpath, dirnames, filenames in os.walk(root, onerror=lambda exc: None):
            dirnames[:] = [name for name in dirnames if name not in _IGNORED_DIRS]
            for filename in filenames:
                relative = Path(dirpath).relative_to(root).joinpath(filename)
                posix_relative = relative.as_posix()
                pattern_without_recursive = pattern[3:] if pattern.startswith("**/") else pattern
                if not (
                    PurePath(posix_relative).match(pattern)
                    or PurePath(posix_relative).match(pattern_without_recursive)
                ):
                    continue
                try:
                    resolved = (Path(dirpath) / filename).resolve()
                except OSError:
                    continue
                if (
                    _is_ignored(resolved)
                    or not resolved.is_relative_to(root)
                    or not resolved.is_file()
                ):
                    continue
                matches.append(str(resolved.relative_to(root)))
        return ToolResult(ok=True, output="\n".join(matches))
