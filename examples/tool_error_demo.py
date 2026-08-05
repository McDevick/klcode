"""Mock-LLM demo: surface a crashing tool through ToolExecutor."""

import asyncio
import sys
from pathlib import Path

_SERVER_DIR = Path(__file__).resolve().parent.parent / "server"
if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))

from kl_server.core.tool_executor import ToolExecutor  # noqa: E402
from kl_server.models.action import ToolResult  # noqa: E402
from kl_server.tools.base import Tool, ToolContext  # noqa: E402
from kl_server.tools.registry import ToolRegistry  # noqa: E402


class CrashingTool(Tool):
    name = "crashy_tool"
    description = "Always raises while executing."
    schema = {"type": "object", "properties": {}}

    async def execute(self, args: dict, ctx: ToolContext) -> ToolResult:
        raise RuntimeError("boom")


async def run_demo() -> ToolResult:
    """Run a crashing tool and return the error result from the executor."""

    registry = ToolRegistry()
    registry.register(CrashingTool())
    executor = ToolExecutor(registry)
    return await executor.execute(
        "crashy_tool",
        {},
        ToolContext(
            workspace=".",
            task_id="demo-tool-error",
            workspace_mode="managed",
        ),
    )


def main() -> None:
    result = asyncio.run(run_demo())
    print(
        "tool_error: ToolExecutor caught the crash and returned a non-ok ToolResult"
    )
    print(f"tool_error: ok={result.ok} error={result.error!r}")
    assert result.ok is False
    assert result.error == "boom"


if __name__ == "__main__":
    main()
