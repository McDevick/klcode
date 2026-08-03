import pytest
from kl_server.providers.base import ProviderRequest
from kl_server.providers.mock import MockProvider
from kl_server.providers.registry import ProviderRegistry


@pytest.mark.asyncio
async def test_mock_provider_returns_sequence():
    provider = MockProvider(responses=["first", "second"])
    first = await provider.complete(ProviderRequest(messages=[], model="mock-model"))
    second = await provider.complete(ProviderRequest(messages=[], model="mock-model"))
    assert (first.text, second.text) == ("first", "second")


def test_registry_requires_known_provider():
    registry = ProviderRegistry()
    with pytest.raises(KeyError):
        registry.get("missing")
