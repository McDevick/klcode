"""MCP client transports for stdio and streamable-http servers."""


class McpTransport:
    """Thin wrapper around the official mcp SDK client for one server."""

    def __init__(self, config: dict):
        self.config = config
        self._client_cm = None
        self._client = None
        self._session = None

    async def connect(self):
        try:
            if "url" in self.config:
                from mcp.client.streamable_http import streamable_http_client

                self._client_cm = streamable_http_client(self.config["url"])
                self._client = await self._client_cm.__aenter__()
            elif "command" in self.config:
                from mcp import ClientSession, StdioServerParameters
                from mcp.client.stdio import stdio_client

                params = StdioServerParameters(
                    command=self.config["command"],
                    args=self.config.get("args", []),
                )
                self._client_cm = stdio_client(params)
                self._client = await self._client_cm.__aenter__()
            else:
                raise ValueError("mcp server config requires 'url' or 'command'")

            from mcp import ClientSession

            self._session = await ClientSession(*self._client).__aenter__()
            await self._session.initialize()
        except Exception as exc:
            await self.close()
            raise ConnectionError("not connected") from exc

    async def call_tool(self, name: str, arguments: dict) -> dict:
        if self._session is None:
            raise ConnectionError("not connected")
        result = await self._session.call_tool(name, arguments)
        return result.model_dump(mode="json")

    async def close(self):
        if self._session is not None:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception:
                pass
            self._session = None
        if self._client_cm is not None:
            try:
                await self._client_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._client_cm = None
            self._client = None
