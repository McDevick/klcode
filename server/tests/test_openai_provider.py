import json

import httpx
import pytest

from kl_server.config.loader import load_app_config
from kl_server.providers.base import ProviderRequest
from kl_server.providers.factory import build_provider_registry
from kl_server.providers.openai_compatible import OpenAICompatibleProvider, ProviderError


class FakeCredentialStore:
    def __init__(self, secret: str | None = "sk-test"):
        self.secret = secret

    def get(self, ref):
        return self.secret if ref == "openai" else None


@pytest.mark.asyncio
async def test_openai_compatible_provider_parses_chat_completion():
    async def handler(request):
        body = json.loads(request.content)
        assert str(request.url).endswith("/chat/completions")
        assert request.headers["Authorization"] == "Bearer sk-test"
        assert body["model"] == "gpt-test"
        assert body["messages"] == [
            {"role": "user", "content": "hi"},
            {"role": "user", "content": "feedback: keep going"},
            {"role": "user", "content": "tool_result: 42"},
        ]
        return httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        base_url="https://example.com/v1",
        api_key="sk-test",
        model="gpt-test",
        client=client,
    )
    response = await provider.complete(
        ProviderRequest(
            messages=[
                {"role": "user", "content": "hi"},
                {"role": "feedback", "content": "keep going"},
                {"role": "tool", "content": "42"},
            ],
            model="gpt-test",
        )
    )
    assert response.text == "hello"


@pytest.mark.asyncio
async def test_openai_compatible_provider_uses_configured_model_when_request_model_empty():
    async def handler(request):
        body = json.loads(request.content)
        assert body["model"] == "gpt-test"
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        base_url="https://example.com/v1",
        api_key="sk-test",
        model="gpt-test",
        client=client,
    )
    response = await provider.complete(ProviderRequest(messages=[], model=""))
    assert response.text == "ok"


@pytest.mark.asyncio
async def test_openai_compatible_provider_rejects_empty_choices():
    async def handler(request):
        return httpx.Response(200, json={"choices": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        base_url="https://example.com/v1",
        api_key="sk-test",
        model="gpt-test",
        client=client,
    )
    with pytest.raises(ProviderError, match="unexpected provider response"):
        await provider.complete(ProviderRequest(messages=[], model="gpt-test"))


@pytest.mark.asyncio
async def test_openai_compatible_provider_wraps_http_error():
    async def handler(request):
        return httpx.Response(500, json={"error": "boom"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        base_url="https://example.com/v1",
        api_key="sk-test",
        model="gpt-test",
        client=client,
    )
    with pytest.raises(ProviderError, match="provider http error: 500"):
        await provider.complete(ProviderRequest(messages=[], model="gpt-test"))


@pytest.mark.asyncio
async def test_provider_close_closes_owned_client():
    provider = OpenAICompatibleProvider(
        base_url="https://example.com/v1",
        api_key=None,
        model="gpt-test",
    )
    assert not provider.client.is_closed
    await provider.close()
    assert provider.client.is_closed


def test_load_app_config_parses_yaml(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "providers:\n"
        "  openai:\n"
        "    type: openai-compatible\n"
        "    base_url: https://example.com/v1\n"
        "    default_model: gpt-test\n"
        "    credential_ref: openai\n",
        encoding="utf-8",
    )
    config = load_app_config(path)
    assert config.providers["openai"].base_url == "https://example.com/v1"


def test_provider_factory_builds_mock_and_openai(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "providers:\n"
        "  openai:\n"
        "    type: openai-compatible\n"
        "    base_url: https://example.com/v1\n"
        "    default_model: gpt-test\n"
        "    credential_ref: openai\n",
        encoding="utf-8",
    )
    config = load_app_config(path)
    registry = build_provider_registry(config, FakeCredentialStore())
    assert registry.get("mock") is not None
    assert registry.get("openai") is not None


def test_provider_factory_raises_when_credential_missing(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "providers:\n"
        "  openai:\n"
        "    type: openai-compatible\n"
        "    base_url: https://example.com/v1\n"
        "    default_model: gpt-test\n"
        "    credential_ref: openai\n",
        encoding="utf-8",
    )
    config = load_app_config(path)
    with pytest.raises(ValueError, match="credential not found: openai"):
        build_provider_registry(config, FakeCredentialStore(secret=None))


def test_provider_factory_rejects_unsupported_type(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "providers:\n"
        "  anthropic:\n"
        "    type: anthropic\n"
        "    base_url: https://example.com/v1\n"
        "    default_model: claude-test\n",
        encoding="utf-8",
    )
    config = load_app_config(path)
    with pytest.raises(ValueError, match="unsupported provider type: anthropic"):
        build_provider_registry(config, FakeCredentialStore())
