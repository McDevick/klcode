import pytest

from kl_server.core.agent_loop import AgentLoop, LoopSettings
from kl_server.core.context import AssembledContext
from kl_server.core.tool_executor import ToolExecutor
from kl_server.extensions import McpTool, register_user_tools
from kl_server.models.action import ToolResult
from kl_server.models.task import Session
from kl_server.providers.mock import MockProvider
from kl_server.tools.base import Tool, ToolContext
from kl_server.tools.registry import ToolRegistry


class FinalTool(Tool):
    name = "final"
    description = "returns final marker"
    schema = {"type": "object", "properties": {}}

    async def execute(self, args, ctx: ToolContext) -> ToolResult:
        return ToolResult(ok=True, output="done")


class SpyAssembler:
    def __init__(self):
        self.calls = 0
        self.last_kwargs = {}

    async def build(self, **kwargs) -> AssembledContext:
        self.calls += 1
        self.last_kwargs = kwargs
        return AssembledContext(text="assembled", used_tokens=10)


class FakeHooks:
    def __init__(self):
        self.events = []

    def run(self, event, payload):
        self.events.append(event)


class FakeSkills:
    def load(self, keywords):
        return "skill-doc"


class FakeMemory:
    async def find(self, tags):
        return []


@pytest.mark.asyncio
async def test_loop_injects_skills_and_fires_hooks():
    registry = ToolRegistry()
    registry.register(FinalTool())
    provider = MockProvider(responses=['{"tool":"final","args":{}}', "DONE"])
    assembler = SpyAssembler()
    hooks = FakeHooks()
    loop = AgentLoop(
        provider=provider,
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=3),
        context=assembler,
        memory=FakeMemory(),
        hooks=hooks,
        skills=FakeSkills(),
    )

    await loop.run(Session(id="s1", workspace="."), "task")

    assert assembler.last_kwargs["skills"] == "skill-doc"
    assert "task_start" in hooks.events
    assert "tool_after" in hooks.events
    assert "task_end" in hooks.events


class FakeMcpAdapter:
    async def tool(self, server, name, args):
        return ToolResult(ok=True, output=f"{server}:{name}")


@pytest.mark.asyncio
async def test_mcp_tool_dispatches_to_adapter():
    tool = McpTool(FakeMcpAdapter())

    result = await tool.execute(
        {"server": "demo", "tool": "echo", "args": {"text": "hi"}},
        ToolContext(workspace="."),
    )

    assert result.ok is True
    assert result.output == "demo:echo"


class PluginTool(Tool):
    name = "plugin_tool"
    description = "plugin tool"
    schema = {}

    async def execute(self, args, ctx: ToolContext) -> ToolResult:
        return ToolResult(ok=True, output="plugin")


class FakePluginLoader:
    def load_tools(self):
        return {"plugin_tool": PluginTool()}


def test_register_user_tools_registers_loaded_plugins():
    registry = ToolRegistry()

    register_user_tools(registry, FakePluginLoader())

    assert registry.get("plugin_tool").name == "plugin_tool"
