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


def test_task_websocket_handles_malformed_json_and_authoritative_task_id():
    client = TestClient(create_app())
    with client.websocket_connect("/ws/tasks/t1") as websocket:
        websocket.send_text("{not-json")
        assert websocket.receive_json()["error"] == "invalid json"
        websocket.send_json({"task_id": "evil", "event": "ok"})
        data = websocket.receive_json()
        assert data["task_id"] == "t1"
        assert data["event"] == "ok"
