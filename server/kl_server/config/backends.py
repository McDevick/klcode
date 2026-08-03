import hashlib
import json
import os
from pathlib import Path
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_AUTO_KEYRING = object()


class SecretStore(Protocol):
    def set(self, ref: str, secret: str) -> None: ...
    def get(self, ref: str) -> str | None: ...
    def has(self, ref: str) -> bool: ...
    def clear(self, ref: str) -> None: ...
    def safe_snapshot(self) -> dict[str, bool]: ...


class EncryptedFileBackend:
    """AES-GCM encrypted JSON file protected by a master password."""

    def __init__(self, path: Path, password: str):
        self.path = Path(path)
        self._key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), b"kl-code", 200_000)

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        blob = self.path.read_bytes()
        nonce, ciphertext = blob[:12], blob[12:]
        plain = AESGCM(self._key).decrypt(nonce, ciphertext, None)
        return json.loads(plain.decode("utf-8"))

    def _write(self, data: dict[str, str]) -> None:
        nonce = os.urandom(12)
        plain = json.dumps(data).encode("utf-8")
        self.path.write_bytes(nonce + AESGCM(self._key).encrypt(nonce, plain, None))

    def set(self, ref, secret): data = self._read(); data[ref] = secret; self._write(data)
    def get(self, ref): return self._read().get(ref)
    def has(self, ref): return ref in self._read()
    def clear(self, ref): data = self._read(); data.pop(ref, None); self._write(data)
    def safe_snapshot(self): return {ref: True for ref in self._read()}


class KeyringBackend:
    """OS keyring backend; falls back to an in-memory store when keyring is unavailable."""

    def __init__(self, service: str = "kl-code", keyring_module=_AUTO_KEYRING):
        self.service = service
        if keyring_module is _AUTO_KEYRING:
            try:
                import keyring as keyring_module
            except Exception:
                keyring_module = None
        self._keyring = keyring_module
        self._memory: dict[str, str] | None = None if keyring_module is not None else {}

    def set(self, ref, secret):
        if self._keyring is not None:
            self._keyring.set_password(self.service, ref, secret)
        else:
            self._memory[ref] = secret

    def get(self, ref):
        if self._keyring is not None:
            return self._keyring.get_password(self.service, ref)
        return self._memory.get(ref)

    def has(self, ref):
        return self.get(ref) is not None

    def clear(self, ref):
        if self._keyring is not None:
            self._keyring.delete_password(self.service, ref)
        else:
            self._memory.pop(ref, None)

    def safe_snapshot(self):
        return {ref: True for ref in (self._memory or {})} if self._keyring is None else {}


def load_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file. Values are PLAINTEXT; only use for local dev and document the risk."""
    result: dict[str, str] = {}
    if not Path(path).exists():
        return result
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result
