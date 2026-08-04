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
    write_plugin(tmp_path, "hello_tool", HELLO_PLUGIN)

    loader = PluginLoader(str(tmp_path))

    assert loader.load_tools()["hello_tool"].name == "hello_tool"


def test_plugin_loader_keys_by_custom_tool_name(tmp_path):
    write_plugin(
        tmp_path,
        "custom_file",
        HELLO_PLUGIN.replace('name = "hello_tool"', 'name = "custom_tool"'),
    )

    tools = PluginLoader(str(tmp_path)).load_tools()

    assert list(tools) == ["custom_tool"]
    assert tools["custom_tool"].name == "custom_tool"


def test_plugin_loader_skips_module_without_tool_export(tmp_path, caplog):
    write_plugin(tmp_path, "no_tool", "VALUE = 1\n")

    loader = PluginLoader(str(tmp_path))

    with caplog.at_level(logging.WARNING, logger="kl_server.plugins.loader"):
        tools = loader.load_tools()

    assert tools == {}
    assert "does not export TOOL" in caplog.text


def test_plugin_loader_continues_after_invalid_plugin(tmp_path, caplog):
    write_plugin(tmp_path, "broken", "def broken(:\n")
    write_plugin(tmp_path, "hello_tool", HELLO_PLUGIN)

    loader = PluginLoader(str(tmp_path))

    with caplog.at_level(logging.WARNING, logger="kl_server.plugins.loader"):
        tools = loader.load_tools()

    assert "hello_tool" in tools
    assert "Failed to load plugin" in caplog.text


def test_plugin_loader_skips_root_flat_files(tmp_path):
    (tmp_path / "hello_tool.py").write_text(HELLO_PLUGIN, encoding="utf-8")

    tools = PluginLoader(str(tmp_path)).load_tools()

    assert tools == {}


def test_plugin_loader_missing_root_returns_empty(tmp_path, caplog):
    loader = PluginLoader(str(tmp_path / "missing"))

    with caplog.at_level(logging.WARNING, logger="kl_server.plugins.loader"):
        assert loader.load_tools() == {}

    assert "not a directory" in caplog.text


def test_plugin_loader_non_directory_root_returns_empty(tmp_path, caplog):
    root = tmp_path / "root"
    root.write_text("not a directory", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="kl_server.plugins.loader"):
        assert PluginLoader(str(root)).load_tools() == {}

    assert "not a directory" in caplog.text


def test_plugin_loader_skips_duplicate_tool_name(tmp_path, caplog):
    write_plugin(tmp_path, "alpha", HELLO_PLUGIN)
    write_plugin(
        tmp_path,
        "beta",
        HELLO_PLUGIN.replace('name = "hello_tool"', 'name = "hello_tool"'),
    )

    with caplog.at_level(logging.WARNING, logger="kl_server.plugins.loader"):
        tools = PluginLoader(str(tmp_path)).load_tools()

    assert list(tools) == ["hello_tool"]
    assert "Duplicate plugin tool name" in caplog.text


def test_plugin_loader_skips_non_string_tool_name(tmp_path, caplog):
    write_plugin(
        tmp_path,
        "numeric_name",
        HELLO_PLUGIN.replace('name = "hello_tool"', "name = 123"),
    )

    with caplog.at_level(logging.WARNING, logger="kl_server.plugins.loader"):
        assert PluginLoader(str(tmp_path)).load_tools() == {}

    assert "non-empty string name" in caplog.text


def test_plugin_loader_name_getter_failure_does_not_block(tmp_path, caplog):
    write_plugin(
        tmp_path,
        "bad_name",
        HELLO_PLUGIN.replace(
            'name = "hello_tool"',
            '@property\n    def name(self):\n        raise RuntimeError("boom")',
        ),
    )
    write_plugin(tmp_path, "hello_tool", HELLO_PLUGIN)

    with caplog.at_level(logging.WARNING, logger="kl_server.plugins.loader"):
        tools = PluginLoader(str(tmp_path)).load_tools()

    assert list(tools) == ["hello_tool"]
    assert "Failed to load plugin" in caplog.text


def test_plugin_loader_imports_helper_from_plugin_directory(tmp_path):
    helper_dir = tmp_path / "hello_tool"
    helper_dir.mkdir(parents=True)
    (helper_dir / "helper.py").write_text(
        "VALUE = 'from-helper'\n",
        encoding="utf-8",
    )
    write_plugin(
        tmp_path,
        "hello_tool",
        "import helper\n"
        "from kl_server.models.action import ToolResult\n"
        "from kl_server.tools.base import Tool, ToolContext\n"
        "class HelloTool(Tool):\n"
        "    name = 'hello_tool'\n"
        "    description = 'hello'\n"
        "    schema = {}\n"
        "    output = helper.VALUE\n"
        "    async def execute(self, args, ctx: ToolContext):\n"
        "        return ToolResult(ok=True, output=self.output)\n"
        "TOOL = HelloTool()\n",
    )

    tools = PluginLoader(str(tmp_path)).load_tools()

    assert tools["hello_tool"].output == "from-helper"


def test_plugin_loader_isolates_helper_modules(tmp_path):
    for name, helper_value in (("alpha", "A"), ("beta", "B")):
        plugin_dir = tmp_path / name
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "helper.py").write_text(
            f"VALUE = '{helper_value}'\n",
            encoding="utf-8",
        )
        (plugin_dir / "tool.py").write_text(
            "import helper\n"
            "from kl_server.models.action import ToolResult\n"
            "from kl_server.tools.base import Tool, ToolContext\n"
            "class HelloTool(Tool):\n"
            f"    name = 'tool_{helper_value.lower()}'\n"
            "    description = 'hello'\n"
            "    schema = {}\n"
            "    output = helper.VALUE\n"
            "    async def execute(self, args, ctx: ToolContext):\n"
            "        return ToolResult(ok=True, output=self.output)\n"
            "TOOL = HelloTool()\n",
            encoding="utf-8",
        )

    tools = PluginLoader(str(tmp_path)).load_tools()

    assert tools["tool_a"].output == "A"
    assert tools["tool_b"].output == "B"


def write_plugin(root, name, source):
    path = root / name / "tool.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path
