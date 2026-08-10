import logging
import os
import sys
import secrets
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def load_or_create_daemon_token(token_path: Path) -> str:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        auth_token = token_path.read_text(encoding="utf-8").strip()
    else:
        auth_token = generate_token()
        with os.fdopen(fd, "w", encoding="utf-8") as token_file:
            token_file.write(auth_token)
    _enforce_token_file_permissions(token_path)
    if not auth_token:
        raise RuntimeError("daemon token file is empty")
    return auth_token


def _enforce_token_file_permissions(token_path: Path) -> None:
    if sys.platform.startswith("win"):
        try:
            os.chmod(token_path, 0o600)
        except OSError as exc:
            logger.warning(
                "could not apply 0600 permissions to %s; Windows may not enforce POSIX modes",
                token_path,
            )
            logger.debug("chmod failure for %s", token_path, exc_info=exc)
        return

    current_mode = token_path.stat().st_mode
    if current_mode & 0o077:
        raise RuntimeError(f"daemon token file permissions are too open: {token_path}")
    try:
        os.chmod(token_path, 0o600)
    except OSError as exc:
        raise RuntimeError(f"could not set daemon token file permissions: {token_path}") from exc
    if token_path.stat().st_mode & 0o077:
        raise RuntimeError(f"daemon token file permissions are too open: {token_path}")
