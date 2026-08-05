from fastapi.testclient import TestClient
from kl_server.api.app import create_app
from kl_server.api.task_events import ApprovalHub, TaskEventBus
from kl_server.core.guardrail import HITLManager


def test_health_route():
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ping_route():
    client = TestClient(create_app())
    response = client.get("/api/v1/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "pong"}


def test_task_websocket_echoes_events():
    client = TestClient(create_app())
    with client.websocket_connect("/ws/tasks/t1") as websocket:
        websocket.send_json({"event": "tool_result"})
        data = websocket.receive_json()
        assert data["task_id"] == "t1"
        assert data["event"] == "tool_result"


def test_task_websocket_broadcasts_to_all_clients():
    client = TestClient(create_app())
    with client.websocket_connect("/ws/tasks/t1") as first:
        with client.websocket_connect("/ws/tasks/t1") as second:
            first.send_json({"event": "tool_result"})
            assert first.receive_json()["event"] == "tool_result"
            assert second.receive_json()["event"] == "tool_result"


def test_task_websocket_broadcasts_are_isolated_per_app():
    client_a = TestClient(create_app())
    client_b = TestClient(create_app())
    with client_a.websocket_connect("/ws/tasks/t1") as first:
        with client_b.websocket_connect("/ws/tasks/t1") as second:
            first.send_json({"event": "from-a"})
            assert first.receive_json()["event"] == "from-a"
            second.send_json({"event": "from-b"})
            assert second.receive_json()["event"] == "from-b"


def test_task_websocket_handles_malformed_json_and_authoritative_task_id():
    client = TestClient(create_app())
    with client.websocket_connect("/ws/tasks/t1") as websocket:
        websocket.send_text("{not-json")
        assert websocket.receive_json()["error"] == "invalid json"
        websocket.send_json({"task_id": "evil", "event": "ok"})
        data = websocket.receive_json()
        assert data["task_id"] == "t1"
        assert data["event"] == "ok"


def test_task_websocket_handles_non_object_and_multiple_messages():
    client = TestClient(create_app())
    with client.websocket_connect("/ws/tasks/t1") as websocket:
        websocket.send_json([1, 2])
        assert websocket.receive_json()["error"] == "payload must be object"
        websocket.send_json({"event": "a"})
        assert websocket.receive_json()["event"] == "a"
        websocket.send_json({"event": "b"})
        assert websocket.receive_json()["event"] == "b"


def test_task_websocket_broadcasts_approval_request():
    client = TestClient(create_app(hitl=HITLManager()))
    with client.websocket_connect("/ws/tasks/t1") as websocket:
        websocket.send_json(
            {
                "event": "approval_request",
                "action_id": "a1",
                "tool": "run_command",
                "args": {"command": "git push --force"},
                "level": "critical",
            }
        )
        data = websocket.receive_json()
        assert data["task_id"] == "t1"
        assert data["event"] == "approval_request"
        assert data["action_id"] == "a1"
        assert data["level"] == "critical"


def test_task_websocket_resolves_approval_decisions_through_hitl():
    hitl = HITLManager()
    hitl.request("a1", "run_command", "git push --force")
    hitl.request("a2", "run_command", "git push --force")
    hitl.request("a3", "run_command", "git push --force")
    client = TestClient(create_app(hitl=hitl))

    with client.websocket_connect("/ws/tasks/t1") as websocket:
        websocket.send_json({"event": "approve", "action_id": "a1"})
        approved = websocket.receive_json()
        assert approved["event"] == "approval_result"
        assert approved["decision"] == "approve"
        assert approved["state"] == "approved"
        assert hitl.is_approved("a1") is True

        websocket.send_json({"event": "reject", "action_id": "a2"})
        rejected = websocket.receive_json()
        assert rejected["event"] == "approval_result"
        assert rejected["decision"] == "reject"
        assert rejected["state"] == "rejected"

        websocket.send_json({"event": "abort", "action_id": "a3"})
        aborted = websocket.receive_json()
        assert aborted["event"] == "approval_result"
        assert aborted["decision"] == "abort"
        assert aborted["state"] == "aborted"


def test_task_websocket_rejects_invalid_decisions_without_crashing():
    hitl = HITLManager()
    hitl.request("a1", "run_command", "git push --force")
    client = TestClient(create_app(hitl=hitl))

    with client.websocket_connect("/ws/tasks/t1") as websocket:
        websocket.send_json({"event": "approve"})
        missing_id = websocket.receive_json()
        assert missing_id["error"] == "action_id is required"

        websocket.send_json({"event": "approve", "action_id": "missing"})
        unknown = websocket.receive_json()
        assert "unknown approval request" in unknown["error"]

        websocket.send_json({"event": "abort", "action_id": 123})
        invalid_id = websocket.receive_json()
        assert invalid_id["error"] == "action_id is required"

        websocket.send_json({"event": "tool_result"})
        normal = websocket.receive_json()
        assert normal["event"] == "tool_result"


def test_task_websocket_requires_hitl_for_decision_messages():
    client = TestClient(create_app())
    with client.websocket_connect("/ws/tasks/t1") as websocket:
        websocket.send_json({"event": "approve", "action_id": "a1"})
        data = websocket.receive_json()
        assert data["error"] == "hitl is not configured"


def test_task_websocket_decision_notifies_approval_hub(monkeypatch):
    bus = TaskEventBus()
    hub = ApprovalHub(bus=bus)
    resolved: list[tuple[str, str]] = []
    monkeypatch.setattr(
        hub, "resolve", lambda action_id, decision: resolved.append((action_id, decision))
    )
    hitl = HITLManager()
    hitl.request("a1", "run_command", "x")
    client = TestClient(create_app(hitl=hitl, bus=bus, hub=hub))

    with client.websocket_connect("/ws/tasks/t1") as websocket:
        websocket.send_json({"event": "approve", "action_id": "a1"})
        websocket.receive_json()

    assert resolved == [("a1", "approve")]
