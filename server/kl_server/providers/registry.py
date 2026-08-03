from kl_server.providers.base import Provider
from kl_server.providers.mock import MockProvider


class ProviderRegistry:
    def __init__(self):
        self._providers: dict[str, Provider] = {"mock": MockProvider()}

    def register(self, name: str, provider: Provider) -> None:
        self._providers[name] = provider

    def get(self, name: str) -> Provider:
        return self._providers[name]
