import asyncio

import pytest

from kl_server.core.agent_loop import AgentLoop, LoopSettings
from kl_server.core.context import AssembledContext
from kl_server.core.tool_executor import ToolExecutor
from kl_server.extensions import register_mcp_tools, register_user_tools
from kl_server.models.action import ToolResult
from kl_server.models.task import Session
from kl_server.providers.mock import MockProvider
from kl_server.skills.loader import SkillLoader
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


class FakeMemory:
    async def find(self, tags):
        return []


@pytest.mark.asyncio
async def test_loop_injects_skills_and_fires_hooks(tmp_path):
    registry = ToolRegistry()
    registry.register(FinalTool())
    provider = MockProvider(responses=['{"tool":"final","args":{}}', "DONE"])
    assembler = SpyAssembler()
    hooks = FakeHooks()
    skill_dir = tmp_path / "skills"
    (skill_dir / "python").mkdir(parents=True)
    (skill_dir / "python" / "SKILL.md").write_text(
        "# Python\nUse pytest",
        encoding="utf-8",
    )
    loop = AgentLoop(
        provider=provider,
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=3),
        context=assembler,
        memory=FakeMemory(),
        hooks=hooks,
        skills=SkillLoader(str(skill_dir)),
    )

    await loop.run(Session(id="s1", workspace="."), "fix python code")

    assert "Use pytest" in assembler.last_kwargs["skills"]
    assert "task_start" in hooks.events
    assert "action_before" in hooks.events
    assert "tool_after" in hooks.events
    assert "feedback_generation" in hooks.events
    assert "task_end" in hooks.events


class FakeMcpAdapter:
    servers = {"demo": {}}

    async def tool(self, server, name, args):
        return ToolResult(ok=True, output=f"{server}:{name}")

    async def list_tools(self, server):
        return [
            {
                "name": "echo",
                "description": "echo text",
                "inputSchema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            }
        ]


@pytest.mark.asyncio
async def test_register_mcp_tools_registers_remote_tools():
    registry = ToolRegistry()
    adapter = FakeMcpAdapter()

    registered = await register_mcp_tools(registry, adapter)

    assert registered == [
        {"server": "demo", "tool": "echo", "name": "mcp_demo_echo"}
    ]
    catalog = {item["name"]: item for item in registry.catalog()}
    assert catalog["mcp_demo_echo"]["schema"]["required"] == ["text"]
    result = await registry.execute(
        "mcp_demo_echo",
        {"text": "hi"},
        ToolContext(workspace="."),
    )
    assert result.ok is True
    assert result.output == "demo:echo"


class SlowMcpAdapter:
    servers = {"slow": {}}

    async def list_tools(self, server):
        await asyncio.sleep(0.1)
        return []


@pytest.mark.asyncio
async def test_register_mcp_tools_skips_slow_server_after_timeout():
    registry = ToolRegistry()

    registered = await register_mcp_tools(
        registry,
        SlowMcpAdapter(),
        discovery_timeout=0.01,
    )

    assert registered == []


class CollisionMcpAdapter:
    servers = {"a_b": {}, "a": {}}

    async def list_tools(self, server):
        schema = {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }
        if server == "a_b":
            return [{"name": "c", "description": "c", "input_schema": schema}]
        return [{"name": "b_c", "description": "b_c", "input_schema": schema}]


@pytest.mark.asyncio
async def test_register_mcp_tools_avoids_cross_server_name_collision():
    registry = ToolRegistry()

    registered = await register_mcp_tools(registry, CollisionMcpAdapter())

    assert len(registered) == 2
    names = [item["name"] for item in registered]
    assert len(set(names)) == 2
    assert len({name.split("_")[-1] for name in names}) == 2
    assert registry.get(names[0]).name != registry.get(names[1]).name


class LongNameMcpAdapter:
    servers = {"server": {}}

    async def list_tools(self, server):
        return [
            {
                "name": "x" * 80,
                "description": "long tool",
                "input_schema": {"type": "object", "properties": {}},
            }
        ]


@pytest.mark.asyncio
async def test_register_mcp_tools_truncates_long_name_with_hash():
    registry = ToolRegistry()

    registered = await register_mcp_tools(registry, LongNameMcpAdapter())

    assert len(registered) == 1
    name = registered[0]["name"]
    assert len(name) <= 64
    assert len(name.split("_")[-1]) == 8


class SchemaMcpAdapter:
    servers = {"demo": {}}

    async def list_tools(self, server):
        return [
            {
                "name": "echo",
                "description": "echo",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "a": {
                            "type": "string",
                            "extra": "removed",
                            "enum": [str(index) for index in range(100)],
                        }
                    },
                    "required": ["a"],
                    "extra": "removed",
                },
            }
        ]


@pytest.mark.asyncio
async def test_register_mcp_tools_whitelists_schema_and_limits_enum():
    registry = ToolRegistry()

    registered = await register_mcp_tools(registry, SchemaMcpAdapter())

    assert len(registered) == 1
    schema = registry.get("mcp_demo_echo").schema
    assert "extra" not in schema
    assert len(schema["properties"]["a"]["enum"]) == 20
    assert schema["required"] == ["a"]


class BadSchemaMcpAdapter:
    servers = {"demo": {}}

    async def list_tools(self, server):
        return [
            {
                "name": "bad",
                "description": "bad",
                "input_schema": {"type": "array"},
            }
        ]


@pytest.mark.asyncio
async def test_register_mcp_tools_skips_invalid_schema():
    registry = ToolRegistry()

    registered = await register_mcp_tools(registry, BadSchemaMcpAdapter())

    assert registered == []
    assert all(
        item["name"] != "mcp_demo_bad"
        for item in registry.catalog()
    )


class DeepSchemaMcpAdapter:
    servers = {"demo": {}}

    async def list_tools(self, server):
        root = {"type": "object"}
        node = root
        for _ in range(200):
            node["properties"] = {"x": {"type": "object"}}
            node = node["properties"]["x"]
        return [
            {
                "name": "deep",
                "description": "deep schema",
                "input_schema": root,
            }
        ]


@pytest.mark.asyncio
async def test_register_mcp_tools_tolerates_deep_schema():
    registry = ToolRegistry()

    registered = await register_mcp_tools(registry, DeepSchemaMcpAdapter())

    assert len(registered) == 1


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
