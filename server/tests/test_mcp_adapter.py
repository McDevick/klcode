import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from kl_server.mcp.adapter import McpAdapter


def test_catalog_includes_server_name_and_full_config():
    adapter = McpAdapter(
        {
            "url-server": {"url": "http://localhost:9999"},
            "command-server": {"command": "python", "args": ["server.py"]},
        }
    )

    assert adapter.catalog() == [
        {"server": "url-server", "url": "http://localhost:9999"},
        {"server": "command-server", "command": "python", "args": ["server.py"]},
    ]


@pytest.mark.asyncio
async def test_tool_returns_not_connected_for_known_server():
    adapter = McpAdapter(
        {
            "my-server": {
                "command": sys.executable,
                "args": ["-c", "raise SystemExit(1)"],
            }
        }
    )

    result = await adapter.tool("my-server", "echo", {"text": "hi"})

    assert result.ok is False
    assert result.output == ""
    assert result.error.startswith("not connected")


class StickyTransport:
    def __init__(self):
        self._session = object()
        self.closed = 0
        self.failures = 1

    @property
    def is_connected(self):
        return self._session is not None

    async def connect(self):
        if self._session is None:
            self._session = object()

    async def call_tool(self, name, arguments):
        if self.failures > 0:
            self.failures -= 1
            raise ConnectionError("not connected: closed")
        if self._session is None:
            raise ConnectionError("not connected: closed")
        return {
            "content": [{"type": "text", "text": "ok"}],
            "isError": False,
        }

    async def list_tools(self):
        return []

    async def close(self):
        self.closed += 1
        self._session = None


class ErrorTextTransport:
    def __init__(self):
        self._session = object()

    @property
    def is_connected(self):
        return self._session is not None

    async def connect(self):
        pass

    async def call_tool(self, name, arguments):
        return {
            "content": [{"type": "text", "text": "ERROR: boom"}],
            "isError": True,
        }

    async def list_tools(self):
        return []

    async def close(self):
        self._session = None


@pytest.mark.asyncio
async def test_tool_is_error_keeps_real_text_output():
    adapter = McpAdapter({"demo": {}})
    adapter._transports["demo"] = ErrorTextTransport()

    result = await adapter.tool("demo", "shell", {})

    assert result.ok is False
    assert result.error is None
    assert result.output == "ERROR: boom"


@pytest.mark.asyncio
async def test_tool_reconnects_after_connection_error():
    adapter = McpAdapter({"demo": {}})
    transport = StickyTransport()
    adapter._transports["demo"] = transport

    first = await adapter.tool("demo", "echo", {})
    second = await adapter.tool("demo", "echo", {})

    assert first.error.startswith("not connected")
    assert second.ok is True
    assert "ok" in second.output
    assert transport.closed == 1


@pytest.mark.asyncio
async def test_tool_returns_unknown_server_error():
    adapter = McpAdapter({"my-server": {"url": "http://localhost:9999"}})

    result = await adapter.tool("missing-server", "echo", {})

    assert result.ok is False
    assert result.output == ""
    assert result.error == "unknown server: missing-server"


MCP_SERVER_SOURCE = """
import anyio
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server


async def list_tools(ctx, params):
    return types.ListToolsResult(
        tools=[
            types.Tool(
                name="echo",
                description="echo text",
                inputSchema={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            )
        ]
    )


async def call_tool(ctx, params):
    text = (params.arguments or {}).get("text", "")
    return types.CallToolResult(content=[types.TextContent(text=f"echo:{text}")])


server = Server(
    "demo",
    on_list_tools=list_tools,
    on_call_tool=call_tool,
)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="demo",
                server_version="0.1.0",
                capabilities=types.ServerCapabilities(tools={}),
            ),
        )


anyio.run(main)
"""


@pytest.mark.asyncio
async def test_tool_calls_stdio_mcp_server(tmp_path):
    script = tmp_path / "mcp_server.py"
    script.write_text(MCP_SERVER_SOURCE, encoding="utf-8")
    adapter = McpAdapter(
        {"demo": {"command": sys.executable, "args": [str(script)]}}
    )

    try:
        result = await adapter.tool("demo", "echo", {"text": "hello"})
    finally:
        await adapter.close()

    assert result.ok is True
    assert result.output == "echo:hello"


@pytest.mark.asyncio
async def test_list_tools_stdio_mcp_server(tmp_path):
    script = tmp_path / "mcp_server.py"
    script.write_text(MCP_SERVER_SOURCE, encoding="utf-8")
    adapter = McpAdapter(
        {"demo": {"command": sys.executable, "args": [str(script)]}}
    )

    try:
        tools = await adapter.list_tools("demo")
    finally:
        await adapter.close()

    assert tools[0]["name"] == "echo"
    assert tools[0]["input_schema"]["required"] == ["text"]


@pytest.mark.asyncio
async def test_tool_reports_not_connected_for_failing_server(tmp_path):
    script = tmp_path / "broken_server.py"
    script.write_text("raise SystemExit(1)\n", encoding="utf-8")
    adapter = McpAdapter(
        {"demo": {"command": sys.executable, "args": [str(script)]}}
    )

    result = await adapter.tool("demo", "echo", {})

    assert result.ok is False
    assert result.error.startswith("not connected")


class MissingMcpEndpoint(BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        pass


@pytest.mark.asyncio
async def test_streamable_http_unavailable_returns_not_connected():
    server = HTTPServer(("127.0.0.1", 0), MissingMcpEndpoint)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        adapter = McpAdapter(
            {
                "demo": {
                    "url": f"http://127.0.0.1:{server.server_address[1]}/mcp"
                }
            }
        )

        result = await adapter.tool("demo", "echo", {})
    finally:
        server.shutdown()
        thread.join()
        server.server_close()

    assert result.ok is False
    assert result.error.startswith("not connected")
