"""Integration tests for task execution over the API and WebSocket bridge."""

import asyncio
import json
import time

from fastapi.testclient import TestClient

from kl_server.api.app import create_app
from kl_server.bootstrap import build_app_dependencies
from kl_server.config.credentials import InMemoryCredentialStore
from kl_server.providers.base import ProviderResponse
from kl_server.providers.mock import MockProvider


def make_deps(tmp_path):
    return build_app_dependencies(
        config_path=tmp_path / "config.yaml",
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )


def create_session_and_task(client, tmp_path, description="do it"):
    session = client.post("/api/v1/sessions", json={"workspace": str(tmp_path)}).json()
    task = client.post(
        "/api/v1/tasks", json={"session_id": session["id"], "description": description}
    ).json()
    return session, task


def wait_for_terminal_status(client, task_id, timeout=5.0):
    deadline = time.time() + timeout
    status = None
    while time.time() < deadline:
        status = client.get(f"/api/v1/tasks/{task_id}").json()["status"]
        if status in ("succeeded", "failed", "canceled"):
            return status
        time.sleep(0.05)
    return status


def test_run_task_executes_with_mock_provider_and_updates_status(tmp_path):
    deps = make_deps(tmp_path)
    deps.loop.provider = MockProvider(
        responses=[
            json.dumps({"tool": "run_command", "args": {"command": "echo ok"}}),
            "DONE",
        ]
    )
    with TestClient(create_app(deps=deps)) as client:
        _, task = create_session_and_task(client, tmp_path)

        response = client.post(f"/api/v1/tasks/{task['id']}/run")

        assert response.status_code == 202
        assert response.json()["status"] == "running"
        assert wait_for_terminal_status(client, task["id"]) == "succeeded"


def test_run_task_streams_events_to_ws_subscribers(tmp_path):
    deps = make_deps(tmp_path)
    deps.loop.provider = MockProvider(
        responses=[
            json.dumps({"tool": "run_command", "args": {"command": "echo ok"}}),
            "DONE",
        ]
    )
    with TestClient(create_app(deps=deps)) as client:
        _, task = create_session_and_task(client, tmp_path)

        with client.websocket_connect(f"/ws/tasks/{task['id']}") as websocket:
            assert client.post(f"/api/v1/tasks/{task['id']}/run").status_code == 202
            events = []
            deadline = time.time() + 5
            while time.time() < deadline:
                data = websocket.receive_json()
                events.append(data)
                if data.get("event") == "task_end":
                    break

    assert any(event["event"] == "loop_start" for event in events)
    assert events[-1]["event"] == "task_end"
    assert events[-1]["status"] == "succeeded"


def test_run_task_approval_flow_resolves_via_websocket(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("remove me", encoding="utf-8")
    deps = make_deps(tmp_path)
    deps.loop.provider = MockProvider(
        responses=[
            json.dumps({"tool": "delete_file", "args": {"path": "target.txt"}}),
            "DONE",
        ]
    )
    with TestClient(create_app(deps=deps)) as client:
        _, task = create_session_and_task(client, tmp_path)

        with client.websocket_connect(f"/ws/tasks/{task['id']}") as websocket:
            assert client.post(f"/api/v1/tasks/{task['id']}/run").status_code == 202
            approval = None
            deadline = time.time() + 5
            while time.time() < deadline and approval is None:
                data = websocket.receive_json()
                if data.get("event") == "approval_request":
                    approval = data
            assert approval is not None
            assert approval["action_id"]
            assert approval["level"] == "dangerous"

            websocket.send_json({"event": "approve", "action_id": approval["action_id"]})
            events = []
            deadline = time.time() + 5
            while time.time() < deadline:
                data = websocket.receive_json()
                events.append(data)
                if data.get("event") == "task_end":
                    break

    assert not target.exists()
    assert events[-1]["event"] == "task_end"
    assert events[-1]["status"] == "succeeded"


def test_run_task_missing_task_returns_404(tmp_path):
    deps = make_deps(tmp_path)
    client = TestClient(create_app(deps=deps))

    response = client.post("/api/v1/tasks/missing/run")

    assert response.status_code == 404


class SlowProvider:
    """Provider that blocks until cancelled; used to observe a running task."""

    async def complete(self, request):
        await asyncio.sleep(30)
        return ProviderResponse(text="DONE")


def test_abort_running_task_cancels_execution_and_marks_canceled(tmp_path):
    deps = make_deps(tmp_path)
    deps.loop.provider = SlowProvider()
    with TestClient(create_app(deps=deps)) as client:
        _, task = create_session_and_task(client, tmp_path)

        assert client.post(f"/api/v1/tasks/{task['id']}/run").status_code == 202
        deadline = time.time() + 5
        status = None
        while time.time() < deadline:
            status = client.get(f"/api/v1/tasks/{task['id']}").json()["status"]
            if status == "running":
                break
            time.sleep(0.05)
        assert status == "running"

        response = client.post(f"/api/v1/tasks/{task['id']}/abort")
        assert response.status_code == 200
        assert response.json()["status"] == "canceled"
        assert wait_for_terminal_status(client, task["id"]) == "canceled"


def test_pause_and_continue_update_task_status(tmp_path):
    deps = make_deps(tmp_path)
    deps.loop.provider = SlowProvider()
    with TestClient(create_app(deps=deps)) as client:
        _, task = create_session_and_task(client, tmp_path)

        assert client.post(f"/api/v1/tasks/{task['id']}/run").status_code == 202
        deadline = time.time() + 5
        while time.time() < deadline:
            status = client.get(f"/api/v1/tasks/{task['id']}").json()["status"]
            if status == "running":
                break
            time.sleep(0.05)
        assert status == "running"

        assert client.post(f"/api/v1/tasks/{task['id']}/pause").status_code == 200
        assert client.get(f"/api/v1/tasks/{task['id']}").json()["status"] == "paused"

        assert client.post(f"/api/v1/tasks/{task['id']}/continue").status_code == 200
        assert client.get(f"/api/v1/tasks/{task['id']}").json()["status"] == "running"

        assert client.post(f"/api/v1/tasks/{task['id']}/abort").status_code == 200
