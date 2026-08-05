from kl_server.providers.base import ProviderRequest, ProviderResponse


class MockProvider:
    def __init__(self, responses: list[str] | None = None):
        self.responses = list(responses or [])
        self.calls: list[ProviderRequest] = []

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        if not self.responses:
            # Without configured responses the agent loop finishes immediately;
            # configure a response list to drive tool actions before finishing.
            return ProviderResponse(text="DONE")
        return ProviderResponse(text=self.responses.pop(0))
