from types import SimpleNamespace

from fastapi.testclient import TestClient

from kl_server.api.app import create_app
from kl_server.bootstrap import build_app_dependencies
from kl_server.config.credentials import InMemoryCredentialStore


def test_bootstrap_registers_providers_tools_and_managers(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "providers:\n"
        "  openai:\n"
        "    type: openai-compatible\n"
        "    base_url: https://example.com/v1\n"
        "    default_model: gpt-test\n"
        "    credential_ref: openai\n",
        encoding="utf-8",
    )
    credentials = InMemoryCredentialStore()
    credentials.set("openai", "test-key")
    deps = build_app_dependencies(
        config_path=config_path,
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=credentials,
    )

    assert deps.provider_registry.get("mock") is not None
    assert deps.provider_registry.get("openai") is not None
    assert deps.tool_registry.get("read_file") is not None
    assert deps.tool_registry.get("task_manage") is not None
    assert deps.sessions is not None
    assert deps.tasks is not None


def test_bootstrap_wires_api_routes_to_deps(tmp_path):
    class FakeSessions:
        def __init__(self):
            self.created = None

        async def create(self, session):
            self.created = session

    class FakeTasks:
        def __init__(self):
            self.created = None

        async def create(self, task):
            self.created = task

    deps = SimpleNamespace(sessions=FakeSessions(), tasks=FakeTasks())
    client = TestClient(create_app(deps=deps))

    created = client.post(
        "/api/v1/sessions",
        json={"workspace": str(tmp_path), "name": "bootstrap"},
    )
    assert created.status_code == 200
    session = created.json()
    assert session["id"]
    assert deps.sessions.created.id == session["id"]
    assert deps.sessions.created.workspace == str(tmp_path)

    task = client.post(
        "/api/v1/tasks",
        json={"session_id": session["id"], "description": "compose server"},
    )
    assert task.status_code == 200
    assert deps.tasks.created.session_id == session["id"]
    assert deps.tasks.created.description == "compose server"
