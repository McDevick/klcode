import json
from pathlib import Path
from typing import Any

from kl_server.models.action import ToolResult
from kl_server.tools.base import Tool, ToolContext


class ReadToolOutputTool(Tool):
    name = "read_tool_output"
    description = "Read a previously persisted full tool output by its output_file reference"
    schema = {
        "type": "object",
        "properties": {"output_file": {"type": "string"}},
        "required": ["output_file"],
    }
    permissions = ["tool_outputs:read"]
    sandbox = {"scope": "global_tool_outputs", "modes": ["read"]}
    timeout = 30.0

    @staticmethod
    def _registration_status(candidate: Path, root: Path) -> str:
        manifest = root / "MANIFEST.jsonl"
        if not manifest.is_file():
            return "missing"
        registered = False
        for line in manifest.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("output_file") != str(candidate):
                continue
            registered = True
            if record.get("deleted_at") or record.get("event") == "deleted":
                return "deleted"
        return "registered" if registered else "missing"

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        output_dir = getattr(ctx, "tool_outputs_dir", None)
        if not output_dir:
            return ToolResult(
                ok=False,
                output="",
                error="tool_outputs_dir is not configured",
            )
        raw = args.get("output_file")
        if not isinstance(raw, str) or not raw.strip():
            return ToolResult(ok=False, output="", error="output_file is required")
        root = Path(output_dir).resolve()
        requested = Path(raw)
        candidate = requested.resolve() if requested.is_absolute() else (root / requested).resolve()
        if not candidate.is_relative_to(root) or candidate.name == "MANIFEST.jsonl":
            return ToolResult(
                ok=False,
                output="",
                error="output file is outside tool_outputs",
            )
        status = self._registration_status(candidate, root)
        if status == "missing":
            return ToolResult(
                ok=False,
                output="",
                error="output file is not registered",
            )
        if status == "deleted" or not candidate.is_file():
            return ToolResult(ok=False, output="", error="output file not found")
        try:
            return ToolResult(
                ok=True,
                output=candidate.read_text(encoding="utf-8", errors="replace"),
            )
        except OSError as exc:
            return ToolResult(ok=False, output="", error=str(exc))