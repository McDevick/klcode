import asyncio
import hashlib
import json
import logging
import re

from kl_server.models.action import ToolResult
from kl_server.mcp.adapter import McpAdapter
from kl_server.plugins.loader import PluginLoader
from kl_server.tools.base import Tool, ToolContext


logger = logging.getLogger(__name__)


def _mcp_remote_tool_name(server: str, tool: str) -> str:
    raw = f"mcp_{server}_{tool}"
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw).strip("_")
    if len(cleaned) <= 64:
        return cleaned or "mcp_remote"
    digest = hashlib.sha256(f"{server}\0{tool}".encode("utf-8")).hexdigest()[:8]
    return f"{cleaned[:55]}_{digest}"


_MAX_MCP_SCHEMA_CHARS = 4096
_MAX_MCP_SCHEMA_DEPTH = 8


def _sanitize_mcp_property_schema(value, depth: int = 0):
    if not isinstance(value, dict):
        return None
    if depth > _MAX_MCP_SCHEMA_DEPTH:
        return None
    cleaned = {}
    if isinstance(value.get("type"), str):
        cleaned["type"] = value["type"]
    if isinstance(value.get("description"), str) and len(value["description"]) <= 200:
        cleaned["description"] = value["description"]
    if isinstance(value.get("enum"), list):
        cleaned["enum"] = value["enum"][:20]
    if isinstance(value.get("items"), dict):
        items = _sanitize_mcp_property_schema(value["items"], depth + 1)
        if items is not None:
            cleaned["items"] = items
    if isinstance(value.get("properties"), dict):
        properties = {}
        for name, prop in value["properties"].items():
            sanitized = _sanitize_mcp_property_schema(prop, depth + 1)
            if sanitized is not None:
                properties[name] = sanitized
        if properties:
            cleaned["properties"] = properties
    if isinstance(value.get("required"), list) and all(
        isinstance(item, str) for item in value["required"]
    ):
        cleaned["required"] = value["required"][:50]
    return cleaned or None


def _sanitize_mcp_schema(schema) -> dict:
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("mcp schema must be an object schema")
    cleaned: dict = {"type": "object"}
    properties = schema.get("properties")
    if properties is not None:
        if not isinstance(properties, dict):
            raise ValueError("mcp schema properties must be an object")
        sanitized_properties = {}
        for name, prop in properties.items():
            sanitized = _sanitize_mcp_property_schema(prop)
            if sanitized is not None:
                sanitized_properties[name] = sanitized
        cleaned["properties"] = sanitized_properties
    required = schema.get("required")
    if required is not None:
        if not isinstance(required, list) or not all(
            isinstance(item, str) for item in required
        ):
            raise ValueError("mcp schema required must be a list of strings")
        cleaned["required"] = required
    if len(json.dumps(cleaned, ensure_ascii=False)) > _MAX_MCP_SCHEMA_CHARS:
        raise ValueError("mcp schema too large")
    return cleaned


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
        self.schema = _sanitize_mcp_schema(
            tool.get("input_schema")
            or tool.get("inputSchema")
            or tool.get("schema")
            or {"type": "object", "properties": {}}
        )
        self.permissions = ["mcp"]
        self.sandbox = {"remote": True}
        self.timeout = None

    async def execute(self, args: dict, ctx: ToolContext) -> ToolResult:
        if not isinstance(args, dict):
            return ToolResult(ok=False, output="", error="mcp tool args must be an object")
        return await self.adapter.tool(
            self.server,
            self.remote_name,
            args,
            workspace=ctx.workspace,
        )


def _set_mcp_discovery_error(adapter, server: str, error: str | None) -> None:
    errors = getattr(adapter, "last_errors", None)
    if errors is None:
        errors = {}
        adapter.last_errors = errors
    if error is None:
        errors.pop(server, None)
    else:
        errors[server] = str(error)[:500]


async def register_mcp_tools(
    registry,
    adapter: McpAdapter,
    servers: list[str] | None = None,
    discovery_timeout: float = 10.0,
) -> list[dict]:
    configured_servers = getattr(adapter, "servers", None)
    if not configured_servers:
        return []
    server_names = servers if servers is not None else list(configured_servers.keys())

    registered: list[dict] = []
    existing_remote_names = {
        tool.name: getattr(tool, "server", None)
        for tool in registry.all()
        if getattr(tool, "server", None) is not None
    }
    used_names = set(existing_remote_names)
    for server in server_names:
        if server not in configured_servers:
            continue
        try:
            tools = await asyncio.wait_for(
                adapter.list_tools(server),
                timeout=discovery_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Timed out discovering MCP tools for %s", server)
            _set_mcp_discovery_error(adapter, server, "discovery timed out")
            continue
        except Exception as exc:
            logger.warning("Failed to discover MCP tools for %s: %s", server, exc)
            _set_mcp_discovery_error(adapter, server, exc)
            continue
        _set_mcp_discovery_error(adapter, server, None)
        for tool in tools:
            remote_name = tool.get("name", "")
            if not remote_name:
                continue
            try:
                remote_tool = McpRemoteTool(adapter, server, tool)
            except Exception as exc:
                logger.warning(
                    "Skipping MCP tool %s on %s: %s",
                    remote_name,
                    server,
                    exc,
                )
                continue
            name = remote_tool.name
            if name in used_names and existing_remote_names.get(name) != server:
                suffix = hashlib.sha256(
                    f"{server}\0{remote_name}".encode("utf-8")
                ).hexdigest()[:8]
                name = f"{name[:55]}_{suffix}"
                remote_tool.name = name
            used_names.add(name)
            registry.register(remote_tool)
            registered.append(
                {
                    "server": server,
                    "tool": remote_name,
                    "name": name,
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
