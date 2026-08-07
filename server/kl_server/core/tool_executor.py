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
        summarizer=None,
    ):
        self.registry = registry
        self.timeout = timeout
        self.max_output_chars = max_output_chars
        self.guardrail = guardrail
        self.summarizer = summarizer
        if self.max_output_chars <= 0:
            raise ValueError("max_output_chars must be positive")

    def _truncate(self, text: str) -> str:
        if len(text) <= self.max_output_chars:
            return text
        marker = "\n...[truncated]"
        if self.max_output_chars <= len(marker):
            return marker[: self.max_output_chars]
        return text[: self.max_output_chars - len(marker)] + marker

    def catalog(self) -> list[dict[str, Any]]:
        return self.registry.catalog()

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
                if hasattr(self.guardrail, "approval_id"):
                    action_id = self.guardrail.approval_id(action)
                else:
                    action_id = f"{ctx.task_id}:{name}:{str(args.get('command', ''))}"
                if hasattr(self.guardrail, "danger") and hasattr(self.guardrail.danger, "classify"):
                    level = self.guardrail.danger.classify(action, workspace_mode=ctx.workspace_mode)
                else:
                    level = "requires_approval"
                return ToolResult(
                    ok=False,
                    output="",
                    error="requires_approval",
                    meta={
                        "action_id": action_id,
                        "tool": name,
                        "args": dict(args),
                        "level": level,
                    },
                )
        return await self._run(name, args, ctx)

    async def execute_approved(
        self,
        name: str,
        args: dict[str, Any],
        ctx: ToolContext,
        action_id: str,
    ) -> ToolResult:
        hitl = getattr(self.guardrail, "hitl", None) if self.guardrail is not None else None
        if hitl is None or not hitl.is_approved(action_id):
            return ToolResult(ok=False, output="", error="not_approved")
        return await self._run(name, args, ctx)

    async def _run(self, name: str, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            result = await asyncio.wait_for(self.registry.execute(name, args, ctx), timeout=self.timeout)
        except asyncio.TimeoutError:
            return ToolResult(ok=False, output="", error="timeout")
        except Exception as exc:
            message = self._truncate(str(exc) or type(exc).__name__)
            return ToolResult(ok=False, output="", error=message)
        raw_output = result.output
        raw_error = result.error
        truncated_output = self._truncate(raw_output)
        truncated_error = self._truncate(raw_error) if raw_error is not None else None
        summary = None
        if self.summarizer is not None:
            try:
                summary = await self.summarizer.summarize(
                    name,
                    args,
                    result,
                    ctx.task_id,
                )
            except Exception:
                summary = None
        return replace(
            result,
            output=truncated_output,
            error=truncated_error,
            summary=summary,
            truncated=len(raw_output) > self.max_output_chars
            or (summary is not None and summary != raw_output),
        )
