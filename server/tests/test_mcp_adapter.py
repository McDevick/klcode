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
    assert result.error == "not connected"


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
    assert "echo:hello" in result.output


@pytest.mark.asyncio
async def test_tool_reports_not_connected_for_failing_server(tmp_path):
    script = tmp_path / "broken_server.py"
    script.write_text("raise SystemExit(1)\n", encoding="utf-8")
    adapter = McpAdapter(
        {"demo": {"command": sys.executable, "args": [str(script)]}}
    )

    result = await adapter.tool("demo", "echo", {})

    assert result.ok is False
    assert result.error == "not connected"


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
    assert result.error == "not connected"
