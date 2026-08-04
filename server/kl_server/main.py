import os
from pathlib import Path

from kl_server.api.app import create_app
from kl_server.core.auth import generate_token

auth_token = generate_token()
token_path = Path.home() / ".kl" / "daemon.token"
token_path.parent.mkdir(parents=True, exist_ok=True)
token_path.write_text(auth_token, encoding="utf-8")
try:
    os.chmod(token_path, 0o600)
except OSError:
    pass

app = create_app(auth_token=auth_token)
