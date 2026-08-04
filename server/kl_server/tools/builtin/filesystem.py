from pathlib import Path
from typing import Any

from kl_server.models.action import ToolResult
from kl_server.tools.base import Tool, ToolContext


class ListDirTool(Tool):
    name = "list_dir"
    description = "List files and directories in a workspace path"
    schema = {"type": "object", "properties": {"path": {"type": "string", "default": "."}}}

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        root = Path(ctx.workspace).resolve()
        target = (root / args.get("path", ".")).resolve()
        if not target.is_relative_to(root):
            return ToolResult(ok=False, output="", error="path outside workspace")
        try:
            lines = [p.name for p in target.iterdir()]
        except OSError as exc:
            return ToolResult(ok=False, output="", error=str(exc))
        return ToolResult(ok=True, output="\n".join(lines))


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read a UTF-8 text file inside the workspace"
    schema = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        root = Path(ctx.workspace).resolve()
        target = (root / args["path"]).resolve()
        if not target.is_relative_to(root):
            return ToolResult(ok=False, output="", error="path outside workspace")
        try:
            content = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return ToolResult(ok=False, output="", error=str(exc))
        return ToolResult(ok=True, output=content)


class WriteFileTool(Tool):
    name = "write_file"
    description = "Write UTF-8 text into a file inside the workspace"
    schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"],
    }

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        root = Path(ctx.workspace).resolve()
        target = (root / args["path"]).resolve()
        if not target.is_relative_to(root):
            return ToolResult(ok=False, output="", error="path outside workspace")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(args["content"], encoding="utf-8")
        except OSError as exc:
            return ToolResult(ok=False, output="", error=str(exc))
        return ToolResult(ok=True, output=str(target))


class DeleteFileTool(Tool):
    name = "delete_file"
    description = "Delete a file inside the workspace"
    schema = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        workspace = Path(ctx.workspace)
        root = workspace.resolve()
        target = (workspace / args["path"]).absolute()
        if not target.resolve().is_relative_to(root):
            return ToolResult(ok=False, output="", error="path outside workspace")
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            return ToolResult(ok=False, output="", error=str(exc))
        return ToolResult(ok=True, output=str(target))
