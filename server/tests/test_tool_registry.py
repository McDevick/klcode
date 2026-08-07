from typing import Any

import pytest
from kl_server.models.action import ToolResult
from kl_server.tools.base import Tool, ToolContext
from kl_server.tools.registry import ToolRegistry


class EchoTool(Tool):
    name = "echo"
    description = "echo args"
    schema = {"type": "object", "properties": {"text": {"type": "string"}}}

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return ToolResult(ok=True, output=args["text"])


class RequiredTextTool(Tool):
    name = "required_text"
    description = "requires text"
    schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return ToolResult(ok=True, output=args["text"])


class OverridingEchoTool(EchoTool):
    description = "overridden echo"

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return ToolResult(ok=True, output="overridden")


@pytest.mark.asyncio
async def test_registry_executes_tool():
    registry = ToolRegistry()
    registry.register(EchoTool())
    result = await registry.execute("echo", {"text": "hi"}, ToolContext(workspace="."))
    assert result.output == "hi"


def test_registry_catalog_returns_tool_metadata():
    tool = EchoTool()
    registry = ToolRegistry()
    registry.register(tool)

    catalog = registry.catalog()

    assert len(catalog) == 1
    assert catalog[0]["name"] == tool.name
    assert catalog[0]["description"] == tool.description
    assert catalog[0]["schema"] == tool.schema
    assert catalog[0]["schema"] is not tool.schema
    assert catalog[0]["permissions"] == []
    assert catalog[0]["sandbox"] == {}
    assert catalog[0]["timeout"] is None


@pytest.mark.asyncio
async def test_registry_schema_error_returns_structured_result():
    registry = ToolRegistry()
    registry.register(RequiredTextTool())

    result = await registry.execute(
        "required_text",
        {},
        ToolContext(workspace="."),
    )

    assert result.ok is False
    assert result.error.startswith("schema_error:")


@pytest.mark.asyncio
async def test_registry_execute_unknown_tool():
    registry = ToolRegistry()

    with pytest.raises(KeyError):
        await registry.execute("missing", {}, ToolContext(workspace="."))


def test_registry_duplicate_name_last_write_wins():
    """Registering another tool with the same name replaces the earlier one (last-write-wins)."""
    registry = ToolRegistry()
    first = EchoTool()
    second = OverridingEchoTool()

    registry.register(first)
    registry.register(second)

    assert registry.get("echo") is second


def test_registry_unknown_tool():
    registry = ToolRegistry()
    with pytest.raises(KeyError):
        registry.get("missing")
