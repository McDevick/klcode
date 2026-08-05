from pathlib import Path

from kl_server.api.app import create_app
from kl_server.core.auth import load_or_create_daemon_token

token_path = Path.home() / ".kl" / "daemon.token"
auth_token = load_or_create_daemon_token(token_path)

app = create_app(auth_token=auth_token)


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8700)
