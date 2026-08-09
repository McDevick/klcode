import asyncio
import json

from kl_server.models.action import ToolResult
from kl_server.mcp.transport import McpTransport


def _mcp_call_text(result: dict) -> str:
    parts = []
    for item in result.get("content") or []:
        if isinstance(item, dict):
            if "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(json.dumps(item, ensure_ascii=False))
    if parts:
        return "\n".join(parts)
    return json.dumps(result, ensure_ascii=False)


class McpAdapter:
    def __init__(self, servers: dict[str, dict]):
        self.servers = servers
        self.last_errors: dict[str, str] = {}
        self._transports: dict[str, McpTransport] = {}

    def catalog(self) -> list[dict]:
        return [{**config, "server": name} for name, config in self.servers.items()]

    async def tool(self, server: str, name: str, args: dict) -> ToolResult:
        config = self.servers.get(server)
        if config is None:
            return ToolResult(ok=False, output="", error=f"unknown server: {server}")
        transport = self._transports.setdefault(server, McpTransport(config))
        try:
            if not transport.is_connected:
                await transport.connect()
            result = await transport.call_tool(name, args)
            output = _mcp_call_text(result)
            if result.get("isError"):
                return ToolResult(ok=False, output=output, error=None)
            return ToolResult(ok=True, output=output)
        except ConnectionError as exc:
            try:
                await transport.close()
            except Exception:
                pass
            return ToolResult(ok=False, output="", error=str(exc) or "not connected")
        except Exception as exc:
            return ToolResult(ok=False, output="", error=str(exc))

    async def list_tools(self, server: str) -> list[dict]:
        config = self.servers.get(server)
        if config is None:
            return []
        transport = self._transports.setdefault(server, McpTransport(config))
        try:
            if not transport.is_connected:
                await transport.connect()
            return await transport.list_tools()
        except asyncio.CancelledError:
            await transport.close()
            raise
        except Exception:
            await transport.close()
            raise

    async def close(self):
        for transport in self._transports.values():
            await transport.close()
        self._transports.clear()
