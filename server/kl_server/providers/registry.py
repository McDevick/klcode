from kl_server.providers.mock import MockProvider


class ProviderRegistry:
    def __init__(self):
        self._providers = {"mock": MockProvider()}

    def register(self, name: str, provider) -> None:
        self._providers[name] = provider

    def get(self, name: str):
        return self._providers[name]
