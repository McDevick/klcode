import importlib
import sys
from pathlib import Path


def test_main_import_does_not_create_runtime_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.chdir(tmp_path)
    module_name = "kl_server.main"
    if module_name in sys.modules:
        del sys.modules[module_name]
    try:
        importlib.import_module(module_name)
    finally:
        sys.modules.pop(module_name, None)

    assert not (tmp_path / ".kl" / "daemon.token").exists()
    assert not (tmp_path / ".kl").exists()


def test_main_runtime_builds_dependencies_and_token(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.chdir(tmp_path)
    from kl_server.main import _build_runtime

    deps, auth_token = _build_runtime()

    assert auth_token
    assert (tmp_path / ".kl" / "daemon.token").read_text(encoding="utf-8") == auth_token
    assert deps.sessions is not None
    assert deps.tasks is not None


from fastapi.testclient import TestClient


def test_main_app_lifespan_builds_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.chdir(tmp_path)
    from kl_server.main import app

    with TestClient(app) as client:
        assert client.app.state.deps is not None
        assert client.app.state.auth_token
        assert client.get("/health").status_code == 200
