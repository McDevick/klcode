"""Integration tests for task execution over the API and WebSocket bridge."""

import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from kl_server.api.app import create_app
from kl_server.api.routes import _execute_task
from kl_server.bootstrap import build_app_dependencies
from kl_server.config.credentials import InMemoryCredentialStore
from kl_server.models.task import Session, Task, TaskStatus
from kl_server.providers.base import ProviderResponse
from kl_server.providers.mock import MockProvider


def make_deps(tmp_path, provider=None):
    deps = build_app_dependencies(
        config_path=tmp_path / "config.yaml",
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )
    if provider is not None:
        deps.provider_registry.register("test", provider)
        deps.config.default_provider = "test"
    return deps


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
    deps = make_deps(
        tmp_path,
        MockProvider(
            responses=[
                json.dumps({"tool": "run_command", "args": {"command": "echo ok"}}),
                "DONE",
            ]
        ),
    )
    with TestClient(create_app(deps=deps)) as client:
        _, task = create_session_and_task(client, tmp_path)

        response = client.post(f"/api/v1/tasks/{task['id']}/run")

        assert response.status_code == 202
        assert response.json()["status"] == "running"
        assert wait_for_terminal_status(client, task["id"]) == "succeeded"


def test_run_task_streams_events_to_ws_subscribers(tmp_path):
    deps = make_deps(
        tmp_path,
        MockProvider(
            responses=[
                json.dumps({"tool": "run_command", "args": {"command": "echo ok"}}),
                "DONE",
            ]
        ),
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
    deps = make_deps(
        tmp_path,
        MockProvider(
            responses=[
                json.dumps({"tool": "delete_file", "args": {"path": "target.txt"}}),
                "DONE",
            ]
        ),
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


class GateProvider:
    """Provider that waits on a test-controlled gate before answering."""

    def __init__(self, gate: asyncio.Event):
        self.gate = gate

    async def complete(self, request):
        await self.gate.wait()
        return ProviderResponse(text="DONE")


def test_abort_running_task_cancels_execution_and_marks_canceled(tmp_path):
    deps = make_deps(tmp_path, SlowProvider())
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
    deps = make_deps(tmp_path, SlowProvider())
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


def test_abort_broadcasts_terminal_event_to_ws_subscribers(tmp_path):
    deps = make_deps(tmp_path, SlowProvider())
    with TestClient(create_app(deps=deps)) as client:
        _, task = create_session_and_task(client, tmp_path)

        with client.websocket_connect(f"/ws/tasks/{task['id']}") as websocket:
            assert client.post(f"/api/v1/tasks/{task['id']}/run").status_code == 202
            deadline = time.time() + 5
            while time.time() < deadline:
                status = client.get(f"/api/v1/tasks/{task['id']}").json()["status"]
                if status == "running":
                    break
                time.sleep(0.05)
            assert status == "running"

            assert client.post(f"/api/v1/tasks/{task['id']}/abort").status_code == 200
            events = []
            deadline = time.time() + 5
            while time.time() < deadline:
                data = websocket.receive_json()
                events.append(data)
                if data.get("event") == "task_end":
                    break

    assert events[-1]["event"] == "task_end"
    assert events[-1]["status"] == "canceled"


def test_approval_abort_marks_task_canceled_not_failed(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("remove me", encoding="utf-8")
    deps = make_deps(
        tmp_path,
        MockProvider(
            responses=[
                json.dumps({"tool": "delete_file", "args": {"path": "target.txt"}}),
                "DONE",
            ]
        ),
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

            websocket.send_json({"event": "abort", "action_id": approval["action_id"]})
            events = []
            deadline = time.time() + 5
            while time.time() < deadline:
                data = websocket.receive_json()
                events.append(data)
                if data.get("event") == "task_end":
                    break

    assert events[-1]["event"] == "task_end"
    assert events[-1]["status"] == "canceled"
    assert client.get(f"/api/v1/tasks/{task['id']}").json()["status"] == "canceled"
    assert target.exists()


def test_run_rejects_already_running_task(tmp_path):
    deps = make_deps(tmp_path, SlowProvider())
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

        response = client.post(f"/api/v1/tasks/{task['id']}/run")
        assert response.status_code == 409

        assert client.post(f"/api/v1/tasks/{task['id']}/abort").status_code == 200
        assert wait_for_terminal_status(client, task["id"]) == "canceled"


def test_abort_rejects_terminal_task(tmp_path):
    deps = make_deps(tmp_path, MockProvider(responses=["DONE"]))
    with TestClient(create_app(deps=deps)) as client:
        _, task = create_session_and_task(client, tmp_path)
        assert client.post(f"/api/v1/tasks/{task['id']}/run").status_code == 202
        assert wait_for_terminal_status(client, task["id"]) == "succeeded"

        response = client.post(f"/api/v1/tasks/{task['id']}/abort")
        assert response.status_code == 409
        assert client.get(f"/api/v1/tasks/{task['id']}").json()["status"] == "succeeded"


def test_paused_task_does_not_finish_until_resumed(tmp_path):
    gate = asyncio.Event()
    deps = make_deps(tmp_path, GateProvider(gate))
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
        gate.set()  # 即使 provider 现在返回 DONE，暂停的任务也不得完成
        time.sleep(0.3)
        assert client.get(f"/api/v1/tasks/{task['id']}").json()["status"] == "paused"

        assert client.post(f"/api/v1/tasks/{task['id']}/continue").status_code == 200
        assert wait_for_terminal_status(client, task["id"]) == "succeeded"


def test_rerun_after_abort_clears_stale_pause_gate(tmp_path):
    gate = asyncio.Event()
    deps = make_deps(tmp_path, GateProvider(gate))
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
        assert client.post(f"/api/v1/tasks/{task['id']}/abort").status_code == 200
        assert wait_for_terminal_status(client, task["id"]) == "canceled"

        # 重新 run 不应继承上次的暂停门控
        assert client.post(f"/api/v1/tasks/{task['id']}/run").status_code == 202
        gate.set()
        assert wait_for_terminal_status(client, task["id"]) == "succeeded"


@pytest.mark.asyncio
async def test_task_final_answer_saved_to_summary(tmp_path):
    deps = make_deps(tmp_path, MockProvider(responses=["DONE: 你好世界"]))
    with TestClient(create_app(deps=deps)) as client:
        _, task = create_session_and_task(client, tmp_path)
        client.post(f"/api/v1/tasks/{task['id']}/run")
        assert wait_for_terminal_status(client, task["id"]) == "succeeded"
    saved = await deps.tasks.get(task["id"])
    assert saved.summary == "你好世界"


class StubLoop:
    def __init__(self, result):
        self.result = result

    async def run(self, session, task, task_id="", workspace_mode="managed"):
        return self.result


class StubTasks:
    def __init__(self):
        self.updates: list[str] = []

    async def update(self, task) -> None:
        self.updates.append(task.status.value)


@pytest.mark.asyncio
async def test_execute_task_maps_needs_approval_status():
    session = Session(id="s1", workspace=".")
    task = Task(id="t1", session_id="s1", description="x")
    deps = SimpleNamespace(loop=StubLoop("NEEDS_APPROVAL"), tasks=StubTasks())

    await _execute_task(deps, session, task, bus=None)

    assert task.status == TaskStatus.AWAITING_APPROVAL
    assert deps.tasks.updates == ["awaiting_approval"]


@pytest.mark.asyncio
async def test_execute_task_marks_max_iterations_as_failed():
    session = Session(id="s1", workspace=".")
    task = Task(id="t1", session_id="s1", description="x")
    deps = SimpleNamespace(loop=StubLoop("MAX_ITERATIONS"), tasks=StubTasks())

    await _execute_task(deps, session, task, bus=None)

    assert task.status == TaskStatus.FAILED
    assert task.summary == "max_iterations reached"


@pytest.mark.asyncio
async def test_unmanaged_task_creates_snapshot_and_records_path(tmp_path):
    deps = make_deps(tmp_path, MockProvider(responses=["DONE"]))
    with TestClient(create_app(deps=deps)) as client:
        session = client.post(
            "/api/v1/sessions",
            json={"workspace": str(tmp_path)},
        ).json()
        task = client.post(
            "/api/v1/tasks",
            json={
                "session_id": session["id"],
                "description": "unmanaged run",
                "workspace_mode": "unmanaged",
            },
        ).json()
        assert client.post(f"/api/v1/tasks/{task['id']}/run").status_code == 202
        assert wait_for_terminal_status(client, task["id"]) == "succeeded"

    saved = await deps.tasks.get(task["id"])
    assert saved.workspace_mode == "unmanaged"
    assert saved.snapshot_path is not None
    assert Path(saved.snapshot_path).is_dir()


@pytest.mark.asyncio
async def test_managed_task_does_not_create_snapshot(tmp_path):
    deps = make_deps(tmp_path, MockProvider(responses=["DONE"]))
    with TestClient(create_app(deps=deps)) as client:
        session = client.post(
            "/api/v1/sessions",
            json={"workspace": str(tmp_path)},
        ).json()
        task = client.post(
            "/api/v1/tasks",
            json={"session_id": session["id"], "description": "managed run"},
        ).json()
        assert client.post(f"/api/v1/tasks/{task['id']}/run").status_code == 202
        assert wait_for_terminal_status(client, task["id"]) == "succeeded"

    saved = await deps.tasks.get(task["id"])
    assert saved.workspace_mode == "git"  # 归一化为 managed，不触发快照
    assert saved.snapshot_path is None
