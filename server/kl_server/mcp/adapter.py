from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from kl_server.models.action import ToolResult
from kl_server.mcp.transport import McpTransport

_MCP_FILESYSTEM_PACKAGE = "@modelcontextprotocol/server-filesystem"


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


def _is_filesystem_server(config: dict[str, Any]) -> bool:
    command = str(config.get("command") or "")
    args = [str(arg) for arg in config.get("args") or []]
    return _MCP_FILESYSTEM_PACKAGE.lower() in " ".join([command, *args]).lower()


def _explicit_directory_args(config: dict[str, Any]) -> list[str]:
    args = [str(arg) for arg in config.get("args") or []]
    return [
        arg.strip()
        for arg in args
        if arg.strip()
        and _MCP_FILESYSTEM_PACKAGE.lower() not in arg.lower()
        and not arg.lstrip().startswith("-")
    ]


def _workspace_in_args(config: dict[str, Any], workspace: str) -> bool:
    resolved = str(Path(workspace).resolve())
    for raw in _explicit_directory_args(config):
        try:
            normalized = str(Path(raw).resolve()).lower()
        except OSError:
            normalized = raw.lower()
        if normalized == resolved.lower():
            return True
    return False


def _config_for_workspace(config: dict[str, Any], workspace: str | None) -> dict[str, Any]:
    if not workspace or not _is_filesystem_server(config):
        return config
    resolved = str(Path(workspace).resolve())
    args = list(config.get("args") or [])
    if not _workspace_in_args(config, resolved):
        args.append(resolved)
    return {**config, "args": args}


class McpAdapter:
    def __init__(self, servers: dict[str, dict]):
        self.servers = servers
        self.last_errors: dict[str, str] = {}
        self._transports: dict[tuple[str, str], McpTransport] = {}

    def catalog(self) -> list[dict]:
        return [{**config, "server": name} for name, config in self.servers.items()]

    def _get_transport(self, server: str, workspace: str | None):
        config = self.servers[server]
        key_workspace = ""
        transport_config = config
        if workspace and _is_filesystem_server(config):
            key_workspace = str(Path(workspace).resolve())
            transport_config = _config_for_workspace(config, workspace)
        key = (server, key_workspace)
        transport = self._transports.get(key)
        if transport is None:
            transport = McpTransport(transport_config)
            self._transports[key] = transport
        return key, transport

    async def tool(
        self,
        server: str,
        name: str,
        args: dict,
        workspace: str | None = None,
    ) -> ToolResult:
        config = self.servers.get(server)
        if config is None:
            return ToolResult(ok=False, output="", error=f"unknown server: {server}")
        key, transport = self._get_transport(server, workspace)
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
        if _is_filesystem_server(config):
            transport = McpTransport(config)
            try:
                if not transport.is_connected:
                    await transport.connect()
                return await transport.list_tools()
            finally:
                await transport.close()
        key, transport = self._get_transport(server, None)
        try:
            if not transport.is_connected:
                await transport.connect()
            return await transport.list_tools()
        except asyncio.CancelledError:
            await transport.close()
            self._transports.pop(key, None)
            raise
        except Exception:
            await transport.close()
            self._transports.pop(key, None)
            raise

    async def release_workspace(self, workspace: str) -> None:
        if not workspace:
            return
        resolved = str(Path(workspace).resolve())
        for key in [key for key in list(self._transports) if key[1] == resolved]:
            transport = self._transports.pop(key, None)
            if transport is not None:
                await transport.close()

    async def release_server(self, server: str) -> None:
        for key in [key for key in list(self._transports) if key[0] == server]:
            transport = self._transports.pop(key, None)
            if transport is not None:
                await transport.close()

    async def close(self):
        for transport in self._transports.values():
            await transport.close()
        self._transports.clear()
