import pytest
from pydantic import ValidationError

from kl_server.config.config import AppConfig, ProviderConfig
from kl_server.config.credentials import InMemoryCredentialStore


def test_credential_store_never_returns_plaintext_config():
    store = InMemoryCredentialStore()
    store.set("openai", "sk-test")
    assert store.has("openai") is True
    assert store.get("openai") == "sk-test"
    assert "sk-test" not in str(store.safe_snapshot())


def test_provider_config_rejects_secret_fields():
    with pytest.raises(ValidationError):
        ProviderConfig(
            name="openai",
            type="openai-compatible",
            base_url="https://example.com/v1",
            default_model="gpt-test",
            credential_ref="openai",
            api_key="sk-should-not-exist",
        )


def test_app_config_roundtrip():
    app = AppConfig(
        providers={
            "openai": ProviderConfig(
                name="openai",
                type="openai-compatible",
                base_url="https://example.com/v1",
                default_model="gpt-test",
                credential_ref="openai",
            )
        },
        default_provider="openai",
    )
    payload = app.model_dump()
    loaded = AppConfig.model_validate(payload)
    assert loaded == app
    assert loaded.providers["openai"].credential_ref == "openai"
