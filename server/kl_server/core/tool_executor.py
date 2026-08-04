import asyncio
from typing import Any

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

    async def execute(self, name: str, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            result = await asyncio.wait_for(self.registry.execute(name, args, ctx), timeout=self.timeout)
        except asyncio.TimeoutError:
            return ToolResult(ok=False, output="", error="timeout")
        except Exception as exc:
            message = str(exc) or type(exc).__name__
            return ToolResult(ok=False, output="", error=message)
        if len(result.output) > self.max_output_chars:
            marker = "\n...[truncated]"
            if self.max_output_chars <= len(marker):
                result.output = marker[: self.max_output_chars]
            else:
                result.output = result.output[: self.max_output_chars - len(marker)] + marker
        return result
