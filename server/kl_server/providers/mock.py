from kl_server.providers.base import ProviderRequest, ProviderResponse


class MockProvider:
    def __init__(self, responses: list[str] | None = None):
        self.responses = list(responses or [])
        self.calls: list[ProviderRequest] = []

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        if not self.responses:
            return ProviderResponse(text="final")
        return ProviderResponse(text=self.responses.pop(0))
