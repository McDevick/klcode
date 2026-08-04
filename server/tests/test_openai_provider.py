import httpx
import pytest

from kl_server.config.loader import load_app_config
from kl_server.providers.base import ProviderRequest
from kl_server.providers.factory import build_provider_registry
from kl_server.providers.openai_compatible import OpenAICompatibleProvider


@pytest.mark.asyncio
async def test_openai_compatible_provider_parses_chat_completion():
    async def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        base_url="https://example.com/v1",
        api_key="sk-test",
        model="gpt-test",
        client=client,
    )
    response = await provider.complete(ProviderRequest(messages=[], model="gpt-test"))
    assert response.text == "hello"


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
    class FakeCredentialStore:
        def get(self, ref):
            return "sk-test" if ref == "openai" else None

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
