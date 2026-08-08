import asyncio
import re
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

from kl_server.models.action import Action
from kl_server.models.action import ToolResult
from kl_server.tools.base import ToolContext
from kl_server.tools.registry import ToolRegistry


def _extract_references(args: dict[str, Any], result: ToolResult) -> list[str]:
    references = list(getattr(result, "references", []) or [])
    for key in ("path", "paths"):
        value = args.get(key)
        if isinstance(value, str) and value:
            references.append(value)
        elif isinstance(value, list):
            references.extend(str(item) for item in value if item)
    patch = args.get("patch")
    if isinstance(patch, str):
        import re

        references.extend(re.findall(r"^--- (\S+)", patch, re.M))
    return list(dict.fromkeys(str(ref) for ref in references))


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        timeout: float = 60.0,
        max_output_chars: int = 20_000,
        guardrail=None,
        summarizer=None,
        logger=None,
        sandbox_policy=None,
    ):
        self.registry = registry
        self.timeout = timeout
        self.max_output_chars = max_output_chars
        self.guardrail = guardrail
        self.summarizer = summarizer
        self.logger = logger
        self.sandbox_policy = sandbox_policy
        if self.max_output_chars <= 0:
            raise ValueError("max_output_chars must be positive")

    def _truncate(self, text: str) -> str:
        if len(text) <= self.max_output_chars:
            return text
        marker = "\n...[truncated]"
        if self.max_output_chars <= len(marker):
            return marker[: self.max_output_chars]
        return text[: self.max_output_chars - len(marker)] + marker

    def _persist_full_output(
        self,
        name: str,
        output: str,
        ctx: ToolContext,
    ) -> str | None:
        try:
            root = Path(ctx.workspace) / ".kl" / "tool_outputs"
            root.mkdir(parents=True, exist_ok=True)
            safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", name)[:40]
            output_path = root / (
                f"{ctx.task_id or 'task'}_{safe_name}_{uuid.uuid4().hex[:8]}.txt"
            )
            output_path.write_text(output, encoding="utf-8", errors="replace")
            return str(output_path)
        except OSError:
            return None

    def catalog(self) -> list[dict[str, Any]]:
        return self.registry.catalog()

    async def execute(self, name: str, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        if self.guardrail is not None:
            try:
                tool = self.registry.get(name)
            except KeyError:
                tool = None
            action = Action(
                tool=name,
                args=args,
                task_id=ctx.task_id,
                workspace=ctx.workspace,
                permissions=list(getattr(tool, "permissions", []) if tool is not None else []),
                sandbox=dict(getattr(tool, "sandbox", {}) if tool is not None else {}),
            )
            try:
                decision = self.guardrail.check(
                    action,
                    workspace_mode=ctx.workspace_mode,
                    workspace=ctx.workspace,
                )
            except Exception as exc:
                message = self._truncate(str(exc) or type(exc).__name__)
                if self.logger is not None:
                    self.logger.write(
                        "governance_decision",
                        {
                            "tool": name,
                            "decision": "error",
                            "error": message,
                            "args": args,
                        },
                        ctx.task_id,
                    )
                return ToolResult(ok=False, output="", error=f"guardrail_error: {message}")
            if self.logger is not None:
                self.logger.write(
                    "governance_decision",
                    {
                        "tool": name,
                        "decision": decision,
                        "args": args,
                        "permissions": action.permissions,
                    },
                    ctx.task_id,
                )
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
            tool = self.registry.get(name)
            timeout = getattr(tool, "timeout", None) or self.timeout
            sandbox_timeout = None
            tool_sandbox = dict(getattr(tool, "sandbox", {}))
            sandbox_policy = self.sandbox_policy
            if sandbox_policy is None and self.guardrail is not None:
                sandbox_policy = getattr(self.guardrail, "sandbox", None)
            if sandbox_policy is not None:
                sandbox_timeout = sandbox_policy.command_timeout()
                tool_sandbox["limits"] = sandbox_policy.resource_limits()
                tool_sandbox["env"] = sandbox_policy.command_env()
            if sandbox_timeout is not None:
                timeout = (
                    min(timeout, sandbox_timeout)
                    if timeout is not None
                    else sandbox_timeout
                )
            tool_ctx = replace(
                ctx,
                permissions=list(getattr(tool, "permissions", [])),
                sandbox=tool_sandbox,
                tool_timeout=timeout,
            )
            result = await asyncio.wait_for(
                self.registry.execute(name, args, tool_ctx),
                timeout=timeout,
            )
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
        output_file = None
        if len(raw_output) > self.max_output_chars:
            output_file = self._persist_full_output(name, raw_output, ctx)
        references = _extract_references(args, result)
        if output_file is not None:
            references.append(output_file)
            result.meta["output_file"] = output_file
        return replace(
            result,
            output=truncated_output,
            error=truncated_error,
            summary=summary,
            truncated=len(raw_output) > self.max_output_chars
            or (summary is not None and summary != raw_output),
            references=references,
            meta=dict(result.meta),
        )
