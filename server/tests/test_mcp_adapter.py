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
    adapter = McpAdapter({"my-server": {"url": "http://localhost:9999"}})

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
