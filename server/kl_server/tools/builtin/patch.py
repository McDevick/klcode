import re
from pathlib import Path
from typing import Any

from kl_server.models.action import ToolResult
from kl_server.tools.base import Tool, ToolContext


def apply_unified_diff(source: str, diff: str) -> str:
    """Apply a minimal unified diff to source text."""
    src_lines = source.splitlines(keepends=True)
    out: list[str] = []
    src_idx = 0
    for line in diff.splitlines(keepends=True):
        if line.startswith(("---", "+++", "\\")):
            continue
        if line.startswith("@@ "):
            match = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line.strip())
            if not match:
                continue
            new_start = int(match.group(2))
            while len(out) < new_start - 1 and src_idx < len(src_lines):
                out.append(src_lines[src_idx])
                src_idx += 1
            continue
        if line.startswith("-"):
            src_idx += 1
        elif line.startswith("+"):
            out.append(line[1:])
        elif line.startswith(" "):
            out.append(line[1:])
            src_idx += 1
    out.extend(src_lines[src_idx:])
    return "".join(out)


class ApplyPatchTool(Tool):
    name = "apply_patch"
    description = "Apply a unified diff to a file inside the workspace"
    schema = {
        "type": "object",
        "properties": {"patch": {"type": "string"}, "path": {"type": "string"}},
        "required": ["patch"],
    }

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        match = re.search(r"^--- (\S+)", args["patch"], re.M)
        if not match:
            return ToolResult(ok=False, output="", error="no file path in patch")
        root = Path(ctx.workspace).resolve()
        target = (root / match.group(1)).resolve()
        if not target.is_relative_to(root):
            return ToolResult(ok=False, output="", error="path outside workspace")
        try:
            target.write_text(
                apply_unified_diff(target.read_text(encoding="utf-8"), args["patch"]),
                encoding="utf-8",
            )
        except (OSError, UnicodeDecodeError) as exc:
            return ToolResult(ok=False, output="", error=str(exc))
        return ToolResult(ok=True, output=str(target))
