from kl_server.models.action import ToolResult


class McpAdapter:
    def __init__(self, servers: dict[str, dict]):
        self.servers = servers

    def catalog(self) -> list[dict]:
        return [{"server": name, **config} for name, config in self.servers.items()]

    async def tool(self, server: str, name: str, args: dict) -> ToolResult:
        if server not in self.servers:
            return ToolResult(ok=False, output="", error=f"unknown server: {server}")
        return ToolResult(ok=False, output="", error="not connected")
