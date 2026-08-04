import logging

from kl_server.plugins.loader import PluginLoader


HELLO_PLUGIN = """\
from kl_server.models.action import ToolResult
from kl_server.tools.base import Tool, ToolContext


class HelloTool(Tool):
    name = "hello_tool"
    description = "hello"
    schema = {}

    async def execute(self, args, ctx: ToolContext):
        return ToolResult(ok=True, output="hello")


TOOL = HelloTool()
"""


def test_plugin_loader_imports_tool_module(tmp_path):
    (tmp_path / "hello_tool.py").write_text(HELLO_PLUGIN, encoding="utf-8")

    loader = PluginLoader(str(tmp_path))

    assert loader.load_tools()["hello_tool"].name == "hello_tool"


def test_plugin_loader_keys_by_custom_tool_name(tmp_path):
    (tmp_path / "custom_file.py").write_text(
        HELLO_PLUGIN.replace('name = "hello_tool"', 'name = "custom_tool"'),
        encoding="utf-8",
    )

    tools = PluginLoader(str(tmp_path)).load_tools()

    assert list(tools) == ["custom_tool"]
    assert tools["custom_tool"].name == "custom_tool"


def test_plugin_loader_skips_module_without_tool_export(tmp_path, caplog):
    (tmp_path / "no_tool.py").write_text("VALUE = 1\n", encoding="utf-8")

    loader = PluginLoader(str(tmp_path))

    with caplog.at_level(logging.WARNING, logger="kl_server.plugins.loader"):
        tools = loader.load_tools()

    assert tools == {}
    assert "does not export TOOL" in caplog.text


def test_plugin_loader_continues_after_invalid_plugin(tmp_path, caplog):
    (tmp_path / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    (tmp_path / "hello_tool.py").write_text(HELLO_PLUGIN, encoding="utf-8")

    loader = PluginLoader(str(tmp_path))

    with caplog.at_level(logging.WARNING, logger="kl_server.plugins.loader"):
        tools = loader.load_tools()

    assert "hello_tool" in tools
    assert "Failed to load plugin" in caplog.text


def test_plugin_loader_skips_init_py(tmp_path):
    (tmp_path / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "hello_tool.py").write_text(HELLO_PLUGIN, encoding="utf-8")

    tools = PluginLoader(str(tmp_path)).load_tools()

    assert list(tools) == ["hello_tool"]
