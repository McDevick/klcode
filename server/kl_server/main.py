import os
from pathlib import Path

from kl_server.api.app import create_app
from kl_server.bootstrap import build_app_dependencies
from kl_server.core.auth import load_or_create_daemon_token


def _global_kl_dir() -> Path:
    kl_dir = Path.home() / ".kl"
    kl_dir.mkdir(parents=True, exist_ok=True)
    return kl_dir


def _build_runtime():
    workspace = Path.cwd()
    kl_dir = _global_kl_dir()
    deps = build_app_dependencies(
        config_path=kl_dir / "config.yaml",
        db_path=kl_dir / "kl.db",
        workspace=str(workspace),
        log_path=kl_dir / "audit.jsonl",
    )
    auth_token = load_or_create_daemon_token(kl_dir / "daemon.token")
    return deps, auth_token


def _daemon_source() -> str:
    return os.environ.get("KL_DAEMON_SOURCE", "manual")


def _idle_timeout() -> float | None:
    try:
        return float(os.environ.get("KL_DAEMON_IDLE_TIMEOUT_SECONDS", "600"))
    except ValueError:
        return 600.0


app = create_app(
    runtime_factory=_build_runtime,
    daemon_source=_daemon_source(),
    idle_timeout=_idle_timeout(),
)


def main() -> None:
    import uvicorn

    # timeout_graceful_shutdown: Ctrl+C 时优雅关闭有上限（默认 None 会无限等待
    # 活动连接，例如挂着的 WebSocket，导致进程成僵尸并占住 8700 端口）。
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8700,
        timeout_graceful_shutdown=3,
    )
