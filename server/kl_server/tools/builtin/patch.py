import re
from pathlib import Path
from typing import Any

from kl_server.models.action import ToolResult
from kl_server.tools.base import Tool, ToolContext


def _strip_diff_prefix(path: str) -> str:
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


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
            old_start = int(match.group(1))
            while src_idx < old_start - 1:
                if src_idx >= len(src_lines):
                    raise ValueError("patch does not apply")
                out.append(src_lines[src_idx])
                src_idx += 1
            if src_idx != old_start - 1:
                raise ValueError("patch does not apply")
            continue
        if line.startswith("-"):
            if src_idx >= len(src_lines) or src_lines[src_idx] != line[1:]:
                raise ValueError("patch does not apply")
            src_idx += 1
        elif line.startswith("+"):
            out.append(line[1:])
        elif line.startswith(" "):
            if src_idx >= len(src_lines) or src_lines[src_idx] != line[1:]:
                raise ValueError("patch does not apply")
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
        matches = re.findall(r"^--- (\S+)", args["patch"], re.M)
        if not matches:
            return ToolResult(ok=False, output="", error="no file path in patch")
        if len(matches) > 1:
            return ToolResult(ok=False, output="", error="multi-file patches are not supported")
        root = Path(ctx.workspace).resolve()
        raw_path = _strip_diff_prefix(args.get("path") or matches[0])
        target = (root / raw_path).resolve()
        if not target.is_relative_to(root):
            return ToolResult(ok=False, output="", error="path outside workspace")
        try:
            target.write_text(
                apply_unified_diff(target.read_text(encoding="utf-8"), args["patch"]),
                encoding="utf-8",
            )
        except (ValueError, OSError, UnicodeDecodeError) as exc:
            return ToolResult(ok=False, output="", error=str(exc))
        return ToolResult(ok=True, output=str(target))
