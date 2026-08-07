import logging
import re

from kl_server.models.action import ToolResult
from kl_server.mcp.adapter import McpAdapter
from kl_server.plugins.loader import PluginLoader
from kl_server.tools.base import Tool, ToolContext


logger = logging.getLogger(__name__)


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


def _mcp_remote_tool_name(server: str, tool: str) -> str:
    raw = f"mcp_{server}_{tool}"
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw).strip("_")
    return cleaned[:64] or "mcp_tool"


class McpRemoteTool(Tool):
    """Concrete Tool registered from an MCP server's list_tools response."""

    def __init__(self, adapter: McpAdapter, server: str, tool: dict):
        self.adapter = adapter
        self.server = server
        self.remote_name = tool.get("name", "")
        self.name = _mcp_remote_tool_name(server, self.remote_name)
        self.description = (
            tool.get("description")
            or f"Call {self.remote_name} from MCP server {self.server}"
        )
        self.schema = dict(
            tool.get("input_schema")
            or tool.get("inputSchema")
            or tool.get("schema")
            or {"type": "object", "properties": {}}
        )

    async def execute(self, args: dict, ctx: ToolContext) -> ToolResult:
        if not isinstance(args, dict):
            return ToolResult(ok=False, output="", error="mcp tool args must be an object")
        return await self.adapter.tool(self.server, self.remote_name, args)


async def register_mcp_tools(
    registry,
    adapter: McpAdapter,
    servers: list[str] | None = None,
) -> list[dict]:
    configured_servers = getattr(adapter, "servers", None)
    if not configured_servers:
        return []
    server_names = servers if servers is not None else list(configured_servers.keys())

    registered: list[dict] = []
    for server in server_names:
        if server not in configured_servers:
            continue
        try:
            tools = await adapter.list_tools(server)
        except Exception as exc:
            logger.warning("Failed to discover MCP tools for %s: %s", server, exc)
            continue
        for tool in tools:
            remote_name = tool.get("name", "")
            if not remote_name:
                continue
            remote_tool = McpRemoteTool(adapter, server, tool)
            registry.register(remote_tool)
            registered.append(
                {
                    "server": server,
                    "tool": remote_name,
                    "name": remote_tool.name,
                }
            )
    return registered


def unregister_mcp_tools(registry, server: str) -> None:
    for tool in list(registry.all()):
        if getattr(tool, "server", None) == server:
            registry.unregister(tool.name)


def register_user_tools(registry, plugin_loader: PluginLoader) -> None:
    for tool in plugin_loader.load_tools().values():
        registry.register(tool)
