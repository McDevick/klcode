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
    description = "Read a UTF-8 text file inside the workspace, optionally by line range"
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "start_line": {"type": "integer", "minimum": 1},
            "end_line": {"type": "integer", "minimum": 1},
        },
        "required": ["path"],
    }

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        root = Path(ctx.workspace).resolve()
        target = (root / args["path"]).resolve()
        if not target.is_relative_to(root):
            return ToolResult(ok=False, output="", error="path outside workspace")
        try:
            content = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return ToolResult(ok=False, output="", error=str(exc))
        lines = content.splitlines()
        has_start = "start_line" in args
        has_end = "end_line" in args
        if not has_start and not has_end:
            return ToolResult(ok=True, output=content)
        start_line = args.get("start_line", 1)
        end_line = args.get("end_line")
        if not isinstance(start_line, int) or start_line < 1:
            return ToolResult(ok=False, output="", error="start_line must be a positive integer")
        if not has_start:
            start_line = 1
        if has_end:
            if not isinstance(end_line, int) or end_line < 1:
                return ToolResult(ok=False, output="", error="end_line must be a positive integer")
            if not has_start:
                end_line = min(end_line, 200)
        else:
            end_line = min(len(lines), start_line + 199)
        if start_line > end_line:
            return ToolResult(ok=False, output="", error="start_line cannot be greater than end_line")
        if end_line - start_line + 1 > 200:
            return ToolResult(ok=False, output="", error="line range exceeds 200 lines")
        if start_line > len(lines):
            return ToolResult(ok=False, output="", error="start_line is beyond end of file")
        actual_end = min(end_line, len(lines))
        output = "\n".join(lines[start_line - 1 : actual_end])
        return ToolResult(ok=True, output=output)


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


class EditFileTool(Tool):
    name = "edit_file"
    description = "Replace a text occurrence or line range in a UTF-8 file inside the workspace"
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old_text": {"type": "string"},
            "new_text": {"type": "string"},
            "occurrence": {"type": "integer", "minimum": 1},
            "start_line": {"type": "integer", "minimum": 1},
            "end_line": {"type": "integer", "minimum": 1},
            "new_content": {"type": "string"},
        },
        "required": ["path"],
    }

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        root = Path(ctx.workspace).resolve()
        target = (root / args["path"]).resolve()
        if not target.is_relative_to(root):
            return ToolResult(ok=False, output="", error="path outside workspace")
        try:
            content = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return ToolResult(ok=False, output="", error=str(exc))

        has_old = "old_text" in args
        has_range = "start_line" in args or "end_line" in args
        if has_old and has_range:
            return ToolResult(
                ok=False,
                output="",
                error="cannot combine old_text with line range",
            )

        if has_old:
            old_text = args.get("old_text")
            new_text = args.get("new_text")
            if not isinstance(old_text, str) or not old_text:
                return ToolResult(ok=False, output="", error="old_text is required")
            if not isinstance(new_text, str):
                return ToolResult(ok=False, output="", error="new_text is required")
            occurrence = args.get("occurrence", 1)
            if not isinstance(occurrence, int) or occurrence < 1:
                return ToolResult(ok=False, output="", error="occurrence must be a positive integer")
            start = 0
            found = -1
            count = 0
            while True:
                found = content.find(old_text, start)
                if found < 0:
                    break
                count += 1
                if count == occurrence:
                    break
                start = found + len(old_text)
            if found < 0:
                return ToolResult(
                    ok=False,
                    output="",
                    error=f"old_text not found (occurrence {occurrence})",
                )
            content = content[:found] + new_text + content[found + len(old_text) :]
        elif has_range:
            lines = content.splitlines()
            has_start = "start_line" in args
            has_end = "end_line" in args
            start_line = args.get("start_line", 1)
            end_line = args.get("end_line")
            if not isinstance(start_line, int) or start_line < 1:
                return ToolResult(ok=False, output="", error="start_line must be a positive integer")
            if not has_start:
                start_line = 1
            if has_end:
                if not isinstance(end_line, int) or end_line < 1:
                    return ToolResult(ok=False, output="", error="end_line must be a positive integer")
                if not has_start:
                    end_line = min(end_line, 200)
            else:
                end_line = min(len(lines), start_line + 199)
            if start_line > end_line:
                return ToolResult(
                    ok=False,
                    output="",
                    error="start_line cannot be greater than end_line",
                )
            if end_line - start_line + 1 > 200:
                return ToolResult(ok=False, output="", error="line range exceeds 200 lines")
            if start_line > len(lines):
                return ToolResult(ok=False, output="", error="start_line is beyond end of file")
            new_content = args.get("new_content", "")
            if not isinstance(new_content, str):
                return ToolResult(ok=False, output="", error="new_content must be a string")
            actual_end = min(end_line, len(lines))
            lines[start_line - 1 : actual_end] = new_content.splitlines()
            content = "\n".join(lines)
        else:
            return ToolResult(
                ok=False,
                output="",
                error="old_text or line range is required",
            )

        try:
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            return ToolResult(ok=False, output="", error=str(exc))
        return ToolResult(ok=True, output=str(target))
