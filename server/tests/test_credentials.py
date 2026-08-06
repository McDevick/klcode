import sys
import types

import pytest
from keyring.errors import PasswordDeleteError
from pydantic import ValidationError

from kl_server.config.backends import (
    CredentialDecryptionError,
    CredentialFileError,
    EncryptedFileBackend,
    KeyringBackend,
)
from kl_server.config.config import AppConfig, ProviderConfig
from kl_server.config.credentials import InMemoryCredentialStore, create_credential_store


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
        key = (service, ref)
        if key not in cls.store:
            raise PasswordDeleteError("missing credential")
        cls.store.pop(key, None)


class ExplodingKeyring:
    @classmethod
    def set_password(cls, service, ref, secret):
        raise RuntimeError("keyring unavailable")

    @classmethod
    def get_password(cls, service, ref):
        raise RuntimeError("keyring unavailable")

    @classmethod
    def delete_password(cls, service, ref):
        raise RuntimeError("keyring unavailable")


class GetFailsKeyring:
    store: dict[tuple, str] = {}

    @classmethod
    def set_password(cls, service, ref, secret):
        cls.store[(service, ref)] = secret

    @classmethod
    def get_password(cls, service, ref):
        raise RuntimeError("keyring unavailable")

    @classmethod
    def delete_password(cls, service, ref):
        cls.store.pop((service, ref), None)


def test_encrypted_file_roundtrip_hides_secret(tmp_path):
    backend = EncryptedFileBackend(tmp_path / "secrets.enc", password="pw")
    backend.set("openai", "sk-test")
    assert backend.get("openai") == "sk-test"
    raw = (tmp_path / "secrets.enc").read_bytes()
    assert b"sk-test" not in raw


def test_encrypted_file_empty_file_raises(tmp_path):
    path = tmp_path / "empty.enc"
    path.write_bytes(b"")

    with pytest.raises(CredentialFileError):
        EncryptedFileBackend(path, password="pw").get("openai")


def test_encrypted_file_wrong_password_raises(tmp_path):
    path = tmp_path / "secrets.enc"
    EncryptedFileBackend(path, password="pw").set("openai", "sk-test")

    with pytest.raises(CredentialDecryptionError):
        EncryptedFileBackend(path, password="wrong").get("openai")


def test_encrypted_file_corrupted_file_raises(tmp_path):
    path = tmp_path / "corrupt.enc"
    path.write_bytes(b"x" * 64)

    with pytest.raises((CredentialFileError, CredentialDecryptionError)):
        EncryptedFileBackend(path, password="pw").get("openai")


def test_keyring_backend_uses_os_keyring():
    backend = KeyringBackend(service="kl-code", keyring_module=FakeKeyring)
    backend.set("openai", "sk-test")
    assert FakeKeyring.store[("kl-code", "openai")] == "sk-test"
    assert backend.available is True
    assert backend.safe_snapshot() == {"openai": True}


def test_keyring_backend_falls_back_in_memory():
    backend = KeyringBackend(service="kl-code", keyring_module=None)
    assert backend.available is False
    backend.set("openai", "sk-test")
    assert backend.get("openai") == "sk-test"
    assert backend.safe_snapshot() == {"openai": True}


def test_keyring_backend_clear_missing_is_idempotent():
    backend = KeyringBackend(service="kl-code", keyring_module=FakeKeyring)
    backend.set("clear-me", "sk-test")

    backend.clear("missing")
    assert backend.available is True

    backend.clear("clear-me")
    assert FakeKeyring.store.get(("kl-code", "clear-me")) is None
    assert backend.available is True

    backend.set("after-clear", "sk-after")
    assert backend.get("after-clear") == "sk-after"


def test_keyring_backend_falls_back_to_memory_on_runtime_error():
    backend = KeyringBackend(service="kl-code", keyring_module=ExplodingKeyring)

    with pytest.warns(RuntimeWarning, match="falling back to in-memory"):
        backend.set("openai", "sk-test")
    assert backend.available is False
    assert backend.get("openai") == "sk-test"

    backend.clear("openai")
    assert backend.get("openai") is None
    assert backend.safe_snapshot() == {}


def test_keyring_backend_password_delete_error_keeps_keyring():
    backend = KeyringBackend(service="kl-code", keyring_module=FakeKeyring)
    backend.set("openai", "sk-test")

    backend.clear("missing")

    assert backend.available is True
    backend.set("after-delete-error", "sk-after")
    assert backend.get("after-delete-error") == "sk-after"


def test_keyring_backend_get_failure_warns_and_resets_snapshot():
    backend = KeyringBackend(service="kl-code", keyring_module=GetFailsKeyring)
    backend.set("openai", "sk-test")
    assert backend.safe_snapshot() == {"openai": True}

    with pytest.warns(RuntimeWarning, match="falling back to in-memory"):
        assert backend.get("openai") is None

    assert backend.available is False
    assert backend.safe_snapshot() == {}

    backend.set("openai", "memory-test")
    assert backend.get("openai") == "memory-test"
    assert backend.safe_snapshot() == {"openai": True}


def test_keyring_backend_auto_detection_ignores_fail_backend(monkeypatch):
    class FailBackend:
        pass

    FailBackend.__module__ = "keyring.backends.fail.test"
    fail_module = types.ModuleType("keyring")
    fail_module.get_keyring = lambda: FailBackend()
    monkeypatch.setitem(sys.modules, "keyring", fail_module)

    backend = KeyringBackend()

    assert backend.available is False


def test_create_credential_store_returns_encrypted_file(tmp_path):
    store = create_credential_store(
        prefer_keyring=False,
        fallback_path=tmp_path / "secrets.enc",
        password="pw",
    )

    assert isinstance(store, EncryptedFileBackend)


def test_create_credential_store_falls_back_with_warning():
    with pytest.warns(RuntimeWarning, match="fell back to in-memory"):
        store = create_credential_store(prefer_keyring=False)

    assert isinstance(store, InMemoryCredentialStore)


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


def test_provider_config_accepts_api_key_field():
    # 本地工具场景：允许把 key 直接写在 config.yaml（.kl/ 已 gitignore），
    # 便于用户一劳永逸配置，无需依赖易失的 keyring/内存凭证。
    provider = ProviderConfig(
        name="openai",
        type="openai-compatible",
        base_url="https://example.com/v1",
        default_model="gpt-test",
        credential_ref="openai",
        api_key="sk-from-config",
    )
    assert provider.api_key == "sk-from-config"


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
