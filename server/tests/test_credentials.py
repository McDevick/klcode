import pytest
from pydantic import ValidationError

from kl_server.config.config import AppConfig, ProviderConfig
from kl_server.config.credentials import InMemoryCredentialStore


def test_safe_snapshot_hides_credentials():
    store = InMemoryCredentialStore()
    store.set("openai", "sk-test")
    assert store.has("openai") is True
    assert store.get("openai") == "sk-test"
    assert "sk-test" not in str(store.safe_snapshot())


def test_credential_store_reports_missing_keys():
    store = InMemoryCredentialStore()
    assert store.get("missing") is None
    assert store.has("missing") is False


def test_credential_store_clear():
    store = InMemoryCredentialStore()
    store.set("openai", "sk-test")
    store.clear("openai")
    assert store.safe_snapshot() == {}

    store.clear("missing")
    assert store.safe_snapshot() == {}


def test_app_config_defaults():
    app = AppConfig()
    assert app.providers == {}
    assert app.default_provider == "mock"


def test_app_config_coerces_provider_dict():
    app = AppConfig(
        providers={
            "openai": {
                "name": "openai",
                "type": "openai-compatible",
                "base_url": "https://example.com/v1",
                "default_model": "gpt-test",
                "credential_ref": "openai",
            }
        }
    )
    assert isinstance(app.providers["openai"], ProviderConfig)
    assert app.providers["openai"].credential_ref == "openai"


def test_app_config_rejects_extra_fields():
    with pytest.raises(ValidationError):
        AppConfig(
            providers={},
            default_provider="mock",
            extra="x",
        )


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
