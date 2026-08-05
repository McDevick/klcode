import pytest
from kl_server.providers.base import ProviderRequest, ProviderResponse
from kl_server.providers.mock import MockProvider
from kl_server.providers.registry import ProviderRegistry


@pytest.mark.asyncio
async def test_mock_provider_returns_sequence():
    provider = MockProvider(responses=["first", "second"])
    first = await provider.complete(ProviderRequest(messages=[], model="mock-model"))
    second = await provider.complete(ProviderRequest(messages=[], model="mock-model"))
    assert (first.text, second.text) == ("first", "second")


@pytest.mark.asyncio
async def test_mock_provider_defaults_to_done():
    provider = MockProvider()
    response = await provider.complete(ProviderRequest(messages=[], model="mock-model"))
    assert response.text == "DONE"


@pytest.mark.asyncio
async def test_mock_provider_records_calls():
    provider = MockProvider(responses=["ok"])
    request = ProviderRequest(messages=[{"role": "user", "content": "hi"}], model="mock-model")
    await provider.complete(request)
    assert provider.calls == [request]


def test_mock_provider_copies_input_responses():
    responses = ["first", "second"]
    provider = MockProvider(responses=responses)
    responses.clear()
    assert provider.responses == ["first", "second"]


def test_registry_requires_known_provider():
    registry = ProviderRegistry()
    with pytest.raises(KeyError):
        registry.get("missing")


def test_registry_defaults_to_mock_and_supports_registration():
    registry = ProviderRegistry()
    assert registry.get("mock") is not None
    provider = MockProvider()
    registry.register("custom", provider)
    assert registry.get("custom") is provider


def test_provider_response_defaults_raw_to_none():
    response = ProviderResponse(text="x")
    assert response.raw is None
