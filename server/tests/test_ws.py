from fastapi.testclient import TestClient
from kl_server.api.app import create_app


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
