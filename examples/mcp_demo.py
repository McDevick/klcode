"""Mock-LLM demo: MCP workspace-aware transport driven by AgentLoop."""

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _demo_import import ensure_kl_server_importable  # noqa: E402
ensure_kl_server_importable()

from kl_server.core.agent_loop import AgentLoop, LoopSettings  # noqa: E402
from kl_server.core.tool_executor import ToolExecutor  # noqa: E402
from kl_server.extensions import register_mcp_tools  # noqa: E402
from kl_server.mcp import adapter as adapter_module  # noqa: E402
from kl_server.mcp.adapter import McpAdapter  # noqa: E402
from kl_server.models.task import Session  # noqa: E402
from kl_server.providers.mock import MockProvider  # noqa: E402
from kl_server.tools.registry import ToolRegistry  # noqa: E402


class RecordingTransport:
    instances = []

    def __init__(self, config):
        self.config = config
        self.closed = 0
        type(self).instances.append(self)

    @property
    def is_connected(self):
        return True

    async def connect(self):
        pass

    async def call_tool(self, name, arguments):
        return {
            "content": [{"type": "text", "text": f"{name}:ok"}],
            "isError": False,
        }

    async def list_tools(self):
        return [
            {
                "name": "list_directory",
                "description": "list directory",
                "inputSchema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            }
        ]

    async def close(self):
        self.closed += 1


async def run_once(registry, workspace: Path) -> str:
    provider = MockProvider(
        responses=[
            '{"tool":"mcp_filesystem_list_directory","args":{"path":"."}}',
            "DONE",
        ]
    )
    loop = AgentLoop(
        provider=provider,
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=3),
    )
    result = await loop.run(
        Session(id=f"demo-mcp-{workspace.name}", workspace=str(workspace)),
        "列出当前目录",
    )
    return result


async def run_demo(first: Path, second: Path):
    original_transport = adapter_module.McpTransport
    adapter_module.McpTransport = RecordingTransport
    RecordingTransport.instances = []
    adapter = McpAdapter(
        {
            "filesystem": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem"],
            }
        }
    )
    registry = ToolRegistry()
    try:
        await register_mcp_tools(registry, adapter)
        first_result = await run_once(registry, first)
        second_result = await run_once(registry, second)

        call_configs = [
            instance.config["args"][-1]
            for instance in RecordingTransport.instances
            if instance.closed == 0 and instance.config["args"]
        ]
        print("filesystem args for workspace A:")
        print(f"  {first.resolve()}")
        print("filesystem args for workspace B:")
        print(f"  {second.resolve()}")
        print(f"workspace transports: {len(set(call_configs))}")
        return first_result, second_result, call_configs
    finally:
        await adapter.close()
        adapter_module.McpTransport = original_transport


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="kl-mcp-demo-") as tmp:
        root = Path(tmp)
        first = root / "first"
        second = root / "second"
        first.mkdir()
        second.mkdir()
        first_result, second_result, call_configs = asyncio.run(
            run_demo(first, second)
        )

    assert first_result == "DONE"
    assert second_result == "DONE"
    assert len(call_configs) >= 2
    assert str(first.resolve()) in call_configs
    assert str(second.resolve()) in call_configs


if __name__ == "__main__":
    main()