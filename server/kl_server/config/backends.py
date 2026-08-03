import hashlib
import json
import os
import warnings
from pathlib import Path
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_AUTO_KEYRING = object()

try:
    import keyring.errors
except ImportError:
    _PasswordDeleteError = Exception
else:
    _PasswordDeleteError = getattr(keyring.errors, "PasswordDeleteError", Exception)


class CredentialFileError(Exception):
    pass


class CredentialDecryptionError(CredentialFileError):
    pass


class SecretStore(Protocol):
    def set(self, ref: str, secret: str) -> None: ...
    def get(self, ref: str) -> str | None: ...
    def has(self, ref: str) -> bool: ...
    def clear(self, ref: str) -> None: ...
    def safe_snapshot(self) -> dict[str, bool]: ...


class EncryptedFileBackend:
    """AES-GCM encrypted JSON file protected by a master password."""

    SALT_SIZE = 16
    NONCE_SIZE = 12
    HEADER_SIZE = SALT_SIZE + NONCE_SIZE
    KDF_ITERATIONS = 200_000

    def __init__(self, path: Path, password: str):
        self.path = Path(path)
        self._password = password

    def _derive_key(self, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac(
            "sha256",
            self._password.encode(),
            salt,
            self.KDF_ITERATIONS,
        )

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        blob = self.path.read_bytes()
        if len(blob) < self.HEADER_SIZE:
            raise CredentialFileError("invalid or corrupted credential file")
        salt = blob[: self.SALT_SIZE]
        nonce = blob[self.SALT_SIZE : self.HEADER_SIZE]
        ciphertext = blob[self.HEADER_SIZE :]
        try:
            plain = AESGCM(self._derive_key(salt)).decrypt(nonce, ciphertext, None)
            data = json.loads(plain.decode("utf-8"))
        except Exception as exc:
            raise CredentialDecryptionError(
                "wrong password or corrupted credential file"
            ) from exc
        if not isinstance(data, dict):
            raise CredentialDecryptionError("wrong password or corrupted credential file")
        return data

    def _write(self, data: dict[str, str]) -> None:
        salt = os.urandom(self.SALT_SIZE)
        nonce = os.urandom(self.NONCE_SIZE)
        plain = json.dumps(data).encode("utf-8")
        ciphertext = AESGCM(self._derive_key(salt)).encrypt(nonce, plain, None)
        self.path.write_bytes(salt + nonce + ciphertext)

    def set(self, ref, secret): data = self._read(); data[ref] = secret; self._write(data)
    def get(self, ref): return self._read().get(ref)
    def has(self, ref): return ref in self._read()
    def clear(self, ref): data = self._read(); data.pop(ref, None); self._write(data)
    def safe_snapshot(self): return {ref: True for ref in self._read()}


class KeyringBackend:
    """OS keyring backend; falls back to an in-memory store when keyring is unavailable."""

    def __init__(self, service: str = "kl-code", keyring_module=_AUTO_KEYRING):
        self.service = service
        self._refs: set[str] = set()
        if keyring_module is _AUTO_KEYRING:
            try:
                import keyring as keyring_module
                keyring_backend = keyring_module.get_keyring()
            except Exception:
                keyring_module = None
            else:
                if ".fail" in keyring_backend.__class__.__module__:
                    keyring_module = None
        self._keyring = keyring_module
        self._memory: dict[str, str] | None = None if keyring_module is not None else {}

    @property
    def available(self) -> bool:
        return self._keyring is not None

    def _fallback_to_memory(self) -> None:
        self._keyring = None
        self._memory = {}
        self._refs = set(self._memory)
        warnings.warn(
            "keyring backend failed; falling back to in-memory",
            RuntimeWarning,
            stacklevel=2,
        )

    def set(self, ref, secret):
        if self._keyring is not None:
            try:
                self._keyring.set_password(self.service, ref, secret)
                self._refs.add(ref)
                return
            except Exception:
                self._fallback_to_memory()
        self._memory[ref] = secret
        self._refs.add(ref)

    def get(self, ref):
        if self._keyring is not None:
            try:
                return self._keyring.get_password(self.service, ref)
            except Exception:
                self._fallback_to_memory()
        return self._memory.get(ref)

    def has(self, ref):
        return self.get(ref) is not None

    def clear(self, ref):
        if self._keyring is not None:
            try:
                self._keyring.delete_password(self.service, ref)
            except _PasswordDeleteError:
                pass
            except Exception:
                self._fallback_to_memory()
        self._refs.discard(ref)
        if self._memory is not None:
            self._memory.pop(ref, None)

    def safe_snapshot(self):
        """Return refs known to this process; for keyring-backed stores use has(ref) for authoritative checks."""
        return {ref: True for ref in self._refs}


def _strip_inline_comment(value: str) -> str:
    quote: str | None = None
    for index, char in enumerate(value):
        if quote is not None:
            if char == quote:
                quote = None
        elif char in ('"', "'"):
            quote = char
        elif char == "#" and (index == 0 or value[index - 1].isspace()):
            return value[:index]
    return value


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
        key = key.strip()
        if not key:
            continue
        value = _strip_inline_comment(value).strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in ('"', "'")
        ):
            value = value[1:-1]
        result[key] = value
    return result
