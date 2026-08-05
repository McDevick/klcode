from pathlib import Path

from kl_server.api.app import create_app
from kl_server.bootstrap import build_app_dependencies
from kl_server.core.auth import load_or_create_daemon_token


def _build_runtime():
    workspace = Path.cwd()
    deps = build_app_dependencies(
        config_path=workspace / ".kl" / "config.yaml",
        db_path=workspace / ".kl" / "kl.db",
        workspace=str(workspace),
        log_path=workspace / ".kl" / "audit.jsonl",
    )
    auth_token = load_or_create_daemon_token(Path.home() / ".kl" / "daemon.token")
    return deps, auth_token


app = create_app(runtime_factory=_build_runtime)


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8700)
