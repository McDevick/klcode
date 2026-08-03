import re
from pathlib import Path
from typing import Any

from kl_server.models.action import ToolResult
from kl_server.tools.base import Tool, ToolContext


class GrepTool(Tool):
    name = "grep"
    description = "Search file contents by regex inside the workspace"
    schema = {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}}, "required": ["pattern"]}

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        root = Path(ctx.workspace).resolve()
        search_root = (root / args.get("path", ".")).resolve()
        if not search_root.is_relative_to(root):
            return ToolResult(ok=False, output="", error="path outside workspace")
        pattern = re.compile(args["pattern"])
        matches = []
        for path in search_root.rglob("*"):
            resolved = path.resolve()
            if not resolved.is_relative_to(root) or not resolved.is_file():
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
        matches = []
        for p in root.glob(args["pattern"]):
            resolved = p.resolve()
            if resolved.is_relative_to(root) and resolved.is_file():
                matches.append(str(resolved.relative_to(root)))
        return ToolResult(ok=True, output="\n".join(matches))
