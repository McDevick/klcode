from kl_server.models.action import ToolResult
from kl_server.mcp.adapter import McpAdapter
from kl_server.plugins.loader import PluginLoader
from kl_server.tools.base import Tool, ToolContext


class McpTool(Tool):
    name = "mcp_tool"
    description = "Call a tool exposed by a configured MCP server"
    schema = {
        "type": "object",
        "properties": {
            "server": {"type": "string"},
            "tool": {"type": "string"},
            "args": {"type": "object"},
        },
        "required": ["server", "tool"],
    }

    def __init__(self, adapter: McpAdapter):
        self.adapter = adapter

    async def execute(self, args: dict, ctx: ToolContext) -> ToolResult:
        if not isinstance(args, dict):
            return ToolResult(ok=False, output="", error="mcp_tool args must be an object")
        missing = [
            key
            for key in ("server", "tool")
            if not isinstance(args.get(key), str) or not args.get(key).strip()
        ]
        if missing:
            return ToolResult(
                ok=False,
                output="",
                error="missing required argument(s): " + ", ".join(missing),
            )
        if "args" in args and not isinstance(args["args"], dict):
            return ToolResult(ok=False, output="", error="mcp_tool 'args' must be an object")
        return await self.adapter.tool(
            args["server"],
            args["tool"],
            args.get("args", {}),
        )


def register_user_tools(registry, plugin_loader: PluginLoader) -> None:
    for tool in plugin_loader.load_tools().values():
        registry.register(tool)
