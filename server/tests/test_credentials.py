import pytest
from pydantic import ValidationError

from kl_server.config.backends import EncryptedFileBackend, KeyringBackend, load_env_file
from kl_server.config.config import AppConfig, ProviderConfig
from kl_server.config.credentials import InMemoryCredentialStore


class FakeKeyring:
    store: dict[tuple, str] = {}

    @classmethod
    def set_password(cls, service, ref, secret):
        cls.store[(service, ref)] = secret

    @classmethod
    def get_password(cls, service, ref):
        return cls.store.get((service, ref))

    @classmethod
    def delete_password(cls, service, ref):
        cls.store.pop((service, ref), None)


def test_encrypted_file_roundtrip_hides_secret(tmp_path):
    backend = EncryptedFileBackend(tmp_path / "secrets.enc", password="pw")
    backend.set("openai", "sk-test")
    assert backend.get("openai") == "sk-test"
    raw = (tmp_path / "secrets.enc").read_bytes()
    assert b"sk-test" not in raw


def test_keyring_backend_uses_os_keyring():
    backend = KeyringBackend(service="kl-code", keyring_module=FakeKeyring)
    backend.set("openai", "sk-test")
    assert FakeKeyring.store[("kl-code", "openai")] == "sk-test"


def test_keyring_backend_falls_back_in_memory():
    backend = KeyringBackend(service="kl-code", keyring_module=None)
    backend.set("openai", "sk-test")
    assert backend.get("openai") == "sk-test"
    assert backend.safe_snapshot() == {"openai": True}


def test_load_env_file_parses_and_marks_plaintext(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# comment\nKL_OPENAI_KEY=sk-env\n", encoding="utf-8")
    assert load_env_file(env) == {"KL_OPENAI_KEY": "sk-env"}


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
