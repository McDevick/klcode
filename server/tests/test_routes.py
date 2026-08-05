from fastapi.testclient import TestClient

from kl_server.api.app import create_app
from kl_server.bootstrap import build_app_dependencies
from kl_server.config.credentials import InMemoryCredentialStore


def make_client():
    return TestClient(create_app())


def make_deps_client(tmp_path):
    deps = build_app_dependencies(
        config_path=tmp_path / "config.yaml",
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )
    return TestClient(create_app(deps=deps))


def create_session(client, workspace="C:\\work", name=None):
    payload = {"workspace": workspace}
    if name is not None:
        payload["name"] = name
    return client.post("/api/v1/sessions", json=payload)


def test_sessions_list_starts_empty():
    client = make_client()

    response = client.get("/api/v1/sessions")

    assert response.status_code == 200
    assert response.json() == []


def test_session_create_get_and_list_returns_generated_id():
    client = make_client()

    created = create_session(client, name="main")
    assert created.status_code == 200
    created_body = created.json()
    assert created_body["id"]
    assert created_body["workspace"] == "C:\\work"
    assert created_body["name"] == "main"
    assert created_body["status"] == "active"

    session_id = created_body["id"]
    fetched = client.get(f"/api/v1/sessions/{session_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == session_id

    listed = client.get("/api/v1/sessions")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [session_id]


def test_session_rename_close_and_delete():
    client = make_client()
    session_id = create_session(client).json()["id"]

    renamed = client.patch(
        f"/api/v1/sessions/{session_id}",
        json={"name": "renamed"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "renamed"
    assert client.get(f"/api/v1/sessions/{session_id}").json()["name"] == "renamed"

    closed = client.post(f"/api/v1/sessions/{session_id}/close")
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert client.get(f"/api/v1/sessions/{session_id}").json()["status"] == "closed"

    deleted = client.delete(f"/api/v1/sessions/{session_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/sessions/{session_id}").status_code == 404


def test_missing_session_returns_not_found():
    client = make_client()

    assert client.get("/api/v1/sessions/missing").status_code == 404
    assert client.patch("/api/v1/sessions/missing", json={"name": "x"}).status_code == 404
    assert client.post("/api/v1/sessions/missing/close").status_code == 404
    assert client.delete("/api/v1/sessions/missing").status_code == 404


def test_task_create_and_get_returns_generated_id():
    client = make_client()

    created = client.post(
        "/api/v1/tasks",
        json={"session_id": "s1", "description": "fix"},
    )
    assert created.status_code == 200
    task = created.json()
    assert task["id"]
    assert task["session_id"] == "s1"
    assert task["description"] == "fix"
    assert task["status"] == "pending"

    fetched = client.get(f"/api/v1/tasks/{task['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == task


def test_missing_task_returns_not_found():
    client = make_client()

    response = client.get("/api/v1/tasks/missing")

    assert response.status_code == 404


def test_task_create_with_missing_session_returns_404_with_deps(tmp_path):
    client = make_deps_client(tmp_path)

    response = client.post(
        "/api/v1/tasks",
        json={"session_id": "missing", "description": "orphan task"},
    )

    assert response.status_code == 404


def test_task_create_with_existing_session_succeeds_with_deps(tmp_path):
    client = make_deps_client(tmp_path)

    session = client.post(
        "/api/v1/sessions",
        json={"workspace": str(tmp_path), "name": "main"},
    ).json()
    response = client.post(
        "/api/v1/tasks",
        json={"session_id": session["id"], "description": "valid task"},
    )

    assert response.status_code == 200
    assert response.json()["session_id"] == session["id"]


def test_config_check_reports_mock_provider():
    client = make_client()

    response = client.post("/api/v1/config/check")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "mock" in body["providers"]


def test_provider_list_and_add():
    client = make_client()

    listed = client.get("/api/v1/providers")
    assert listed.status_code == 200
    assert any(item["name"] == "mock" for item in listed.json())

    provider = {
        "name": "acme",
        "type": "openai-compatible",
        "base_url": "http://127.0.0.1:9999/v1",
        "default_model": "gpt-test",
    }
    added = client.post("/api/v1/providers", json=provider)
    assert added.status_code == 200
    assert added.json()["name"] == "acme"

    listed = client.get("/api/v1/providers")
    assert any(item["name"] == "acme" for item in listed.json())


def test_models_route_includes_mock_model():
    client = make_client()

    response = client.get("/api/v1/models")

    assert response.status_code == 200
    assert any(item["name"] == "mock-model" for item in response.json())


def test_key_routes_only_return_configured_status_and_never_secret():
    client = make_client()
    secret = "sk-super-secret"

    configured = client.post("/api/v1/keys/openai", json={"secret": secret})
    assert configured.status_code == 200
    assert configured.json() == {"configured": True}
    assert secret not in configured.text

    status = client.get("/api/v1/keys/openai")
    assert status.status_code == 200
    assert status.json() == {"configured": True}
    assert secret not in status.text

    listed = client.get("/api/v1/keys")
    assert listed.status_code == 200
    assert "openai" in listed.json()["configured"]
    assert secret not in listed.text

    cleared = client.delete("/api/v1/keys/openai")
    assert cleared.status_code == 200
    assert cleared.json() == {"configured": False}
    assert secret not in cleared.text
    assert client.get("/api/v1/keys/openai").json() == {"configured": False}


def test_route_state_is_isolated_per_app_instance():
    client_a = make_client()
    client_b = make_client()

    session_id = create_session(client_a).json()["id"]
    task = client_a.post(
        "/api/v1/tasks",
        json={"session_id": session_id, "description": "isolated"},
    ).json()
    client_a.post("/api/v1/providers", json={
        "name": "acme",
        "type": "openai-compatible",
        "base_url": "http://127.0.0.1:9999/v1",
        "default_model": "gpt-test",
    })
    client_a.post("/api/v1/keys/openai", json={"secret": "sk-secret"})

    assert client_b.get("/api/v1/sessions").json() == []
    assert client_b.get(f"/api/v1/tasks/{task['id']}").status_code == 404
    assert all(item["name"] != "acme" for item in client_b.get("/api/v1/providers").json())
    assert client_b.get("/api/v1/keys/openai").json() == {"configured": False}


def test_new_routes_are_protected_by_auth_middleware():
    client = TestClient(create_app(auth_token="s3cret"))

    unauthorized = client.post(
        "/api/v1/sessions",
        json={"workspace": "C:\\work"},
    )
    assert unauthorized.status_code == 401

    authorized = client.post(
        "/api/v1/sessions",
        json={"workspace": "C:\\work"},
        headers={"Authorization": "Bearer s3cret"},
    )
    assert authorized.status_code == 200
