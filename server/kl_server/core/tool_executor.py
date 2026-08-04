import asyncio
from dataclasses import replace
from typing import Any

from kl_server.models.action import Action
from kl_server.models.action import ToolResult
from kl_server.tools.base import ToolContext
from kl_server.tools.registry import ToolRegistry


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        timeout: float = 60.0,
        max_output_chars: int = 20_000,
        guardrail=None,
    ):
        self.registry = registry
        self.timeout = timeout
        self.max_output_chars = max_output_chars
        self.guardrail = guardrail
        if self.max_output_chars <= 0:
            raise ValueError("max_output_chars must be positive")

    def _truncate(self, text: str) -> str:
        if len(text) <= self.max_output_chars:
            return text
        marker = "\n...[truncated]"
        if self.max_output_chars <= len(marker):
            return marker[: self.max_output_chars]
        return text[: self.max_output_chars - len(marker)] + marker

    async def execute(self, name: str, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        if self.guardrail is not None:
            action = Action(tool=name, args=args, task_id=ctx.task_id, workspace=ctx.workspace)
            try:
                decision = self.guardrail.check(action, workspace_mode=ctx.workspace_mode)
            except Exception as exc:
                message = self._truncate(str(exc) or type(exc).__name__)
                return ToolResult(ok=False, output="", error=f"guardrail_error: {message}")
            if decision == "rejected":
                return ToolResult(ok=False, output="", error="rejected")
            if decision == "requires_approval":
                return ToolResult(
                    ok=False,
                    output="",
                    error="requires_approval",
                    meta={"tool": name, "args": dict(args)},
                )
        try:
            result = await asyncio.wait_for(self.registry.execute(name, args, ctx), timeout=self.timeout)
        except asyncio.TimeoutError:
            return ToolResult(ok=False, output="", error="timeout")
        except Exception as exc:
            message = self._truncate(str(exc) or type(exc).__name__)
            return ToolResult(ok=False, output="", error=message)
        return replace(
            result,
            output=self._truncate(result.output),
            error=self._truncate(result.error) if result.error is not None else None,
        )
