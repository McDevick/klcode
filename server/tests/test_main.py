import importlib
import sys
from pathlib import Path

import pytest


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
    assert deps.config_path == str(tmp_path / ".kl" / "config.yaml")
    assert deps.db.path == tmp_path / ".kl" / "kl.db"
    assert deps.memory.path == tmp_path / ".kl" / "memory.db"
    assert deps.logger.path == tmp_path / ".kl" / "audit.jsonl"


from fastapi.testclient import TestClient


def test_main_ignores_project_config_when_global_config_exists(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "project"
    project_kl = project / ".kl"
    project_kl.mkdir(parents=True)
    (project_kl / "config.yaml").write_text("[invalid yaml", encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.chdir(project)

    from kl_server.main import _build_runtime

    deps, _ = _build_runtime()

    assert deps.config_path == str(home / ".kl" / "config.yaml")
    assert (project_kl / "config.yaml").read_text(encoding="utf-8") == "[invalid yaml"


@pytest.mark.asyncio
async def test_main_lifespan_marks_stale_tasks_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.chdir(tmp_path)
    from fastapi.testclient import TestClient

    from kl_server.api.app import create_app
    from kl_server.main import _build_runtime
    from kl_server.models.task import Session, Task, TaskStatus

    deps, auth_token = _build_runtime()
    await deps.sessions.create(Session(id="s1", workspace=str(tmp_path)))
    await deps.tasks.create(
        Task(id="t1", session_id="s1", description="x", status=TaskStatus.RUNNING)
    )

    def factory():
        return deps, auth_token

    with TestClient(create_app(runtime_factory=factory)) as client:
        assert client.app.state.deps is deps
        task = await deps.tasks.get("t1")
        assert task.status == TaskStatus.FAILED
        assert "daemon restarted" in task.summary


def test_main_app_lifespan_builds_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.chdir(tmp_path)
    from kl_server.main import app

    with TestClient(app) as client:
        assert client.app.state.deps is not None
        assert client.app.state.auth_token
        assert client.get("/health").status_code == 200
