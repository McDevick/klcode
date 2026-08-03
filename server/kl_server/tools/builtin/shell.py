import json
import subprocess
from typing import Any

from kl_server.models.action import ToolResult
from kl_server.tools.base import Tool, ToolContext


class RunCommandTool(Tool):
    name = "run_command"
    description = "Run a shell command and return exit code, stdout, and stderr as JSON"
    schema = {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            proc = subprocess.run(
                args["command"],
                shell=True,
                cwd=ctx.workspace,
                capture_output=True,
                text=True,
                timeout=60,
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            return ToolResult(ok=False, output="", error="timeout")
        except OSError as exc:
            return ToolResult(ok=False, output="", error=str(exc))
        payload = {
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-8000:],
            "stderr": proc.stderr[-8000:],
        }
        return ToolResult(ok=True, output=json.dumps(payload, ensure_ascii=False))
