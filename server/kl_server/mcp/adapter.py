import json

from kl_server.models.action import ToolResult
from kl_server.mcp.transport import McpTransport


class McpAdapter:
    def __init__(self, servers: dict[str, dict]):
        self.servers = servers
        self._transports: dict[str, McpTransport] = {}

    def catalog(self) -> list[dict]:
        return [{**config, "server": name} for name, config in self.servers.items()]

    async def tool(self, server: str, name: str, args: dict) -> ToolResult:
        config = self.servers.get(server)
        if config is None:
            return ToolResult(ok=False, output="", error=f"unknown server: {server}")
        transport = self._transports.setdefault(server, McpTransport(config))
        try:
            if transport._session is None:
                await transport.connect()
            result = await transport.call_tool(name, args)
            output = json.dumps(result, ensure_ascii=False)
            if result.get("isError"):
                return ToolResult(ok=False, output=output, error="mcp_tool_error")
            return ToolResult(ok=True, output=output)
        except ConnectionError:
            return ToolResult(ok=False, output="", error="not connected")
        except Exception as exc:
            return ToolResult(ok=False, output="", error=str(exc))

    async def list_tools(self, server: str) -> list[dict]:
        config = self.servers.get(server)
        if config is None:
            return []
        transport = self._transports.setdefault(server, McpTransport(config))
        if transport._session is None:
            await transport.connect()
        return await transport.list_tools()

    async def close(self):
        for transport in self._transports.values():
            await transport.close()
        self._transports.clear()
