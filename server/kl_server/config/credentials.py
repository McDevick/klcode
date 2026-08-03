from typing import Protocol

from kl_server.config.backends import EncryptedFileBackend, KeyringBackend


class CredentialStore(Protocol):
    def set(self, ref: str, secret: str) -> None: ...
    def get(self, ref: str) -> str | None: ...
    def has(self, ref: str) -> bool: ...
    def clear(self, ref: str) -> None: ...
    def safe_snapshot(self) -> dict[str, bool]: ...


class InMemoryCredentialStore:
    def __init__(self):
        self._secrets: dict[str, str] = {}

    def set(self, ref: str, secret: str) -> None:
        self._secrets[ref] = secret

    def get(self, ref: str) -> str | None:
        return self._secrets.get(ref)

    def has(self, ref: str) -> bool:
        return ref in self._secrets

    def clear(self, ref: str) -> None:
        self._secrets.pop(ref, None)

    def safe_snapshot(self) -> dict[str, bool]:
        return {ref: True for ref in self._secrets}


def create_credential_store(prefer_keyring: bool = True, fallback_path=None, password: str = ""):
    if prefer_keyring:
        store = KeyringBackend(service="kl-code")
        if store._keyring is not None:
            return store
    if fallback_path is not None and password:
        return EncryptedFileBackend(fallback_path, password=password)
    return InMemoryCredentialStore()
