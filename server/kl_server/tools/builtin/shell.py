import asyncio
import json
import subprocess
from typing import Any

from kl_server.models.action import ToolResult
from kl_server.tools.base import Tool, ToolContext


class RunCommandTool(Tool):
    name = "run_command"
    description = "Run a shell command and return exit code, stdout, and stderr as JSON"
    schema = {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}
    permissions = ["command", "unmanaged_escalation"]
    sandbox = {"allow": [], "deny": []}
    timeout = 120.0

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        timeout = getattr(ctx, "tool_timeout", None) or 60
        sandbox = getattr(ctx, "sandbox", {})
        limits = sandbox.get("limits", {})
        command_env = sandbox.get("env")
        preexec_fn = None
        try:
            import resource
        except ImportError:
            pass
        else:
            def apply_limits():
                cpu_seconds = limits.get("cpu_seconds")
                memory_mb = limits.get("memory_mb")
                if cpu_seconds is not None:
                    cpu_limit = int(cpu_seconds)
                    resource.setrlimit(
                        resource.RLIMIT_CPU,
                        (cpu_limit, cpu_limit),
                    )
                if memory_mb is not None:
                    memory_limit = int(memory_mb) * 1024 * 1024
                    resource.setrlimit(
                        resource.RLIMIT_AS,
                        (memory_limit, memory_limit),
                    )

            preexec_fn = apply_limits
        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                args["command"],
                shell=True,
                cwd=ctx.workspace,
                capture_output=True,
                text=True,
                env=command_env,
                timeout=timeout,
                errors="replace",
                preexec_fn=preexec_fn,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(ok=False, output="", error="timeout")
        except OSError as exc:
            return ToolResult(ok=False, output="", error=str(exc))
        payload = {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "truncated": False,
        }
        return ToolResult(ok=True, output=json.dumps(payload, ensure_ascii=False))