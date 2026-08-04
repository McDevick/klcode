import os
from pathlib import Path

from kl_server.api.app import create_app
from kl_server.core.auth import generate_token

token_path = Path.home() / ".kl" / "daemon.token"
token_path.parent.mkdir(parents=True, exist_ok=True)
try:
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    auth_token = token_path.read_text(encoding="utf-8").strip()
else:
    auth_token = generate_token()
    with os.fdopen(fd, "w", encoding="utf-8") as token_file:
        token_file.write(auth_token)
    try:
        os.chmod(token_path, 0o600)
    except OSError:
        pass

if not auth_token:
    raise RuntimeError("daemon token file is empty")

app = create_app(auth_token=auth_token)
