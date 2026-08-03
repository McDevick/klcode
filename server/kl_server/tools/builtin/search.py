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
        pattern = re.compile(args["pattern"])
        matches = []
        for path in root.rglob("*"):
            if path.is_file():
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if pattern.search(text):
                    matches.append(str(path.relative_to(root)))
        return ToolResult(ok=True, output="\n".join(matches))


class GlobTool(Tool):
    name = "glob"
    description = "Find files matching a glob pattern inside the workspace"
    schema = {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        root = Path(ctx.workspace).resolve()
        matches = [str(p.relative_to(root)) for p in root.glob(args["pattern"]) if p.is_file()]
        return ToolResult(ok=True, output="\n".join(matches))
