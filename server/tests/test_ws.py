from fastapi.testclient import TestClient
from kl_server.api.app import create_app


def test_health_route():
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_task_websocket_echoes_events():
    client = TestClient(create_app())
    with client.websocket_connect("/ws/tasks/t1") as websocket:
        websocket.send_json({"event": "tool_result"})
        data = websocket.receive_json()
        assert data["task_id"] == "t1"
        assert data["event"] == "tool_result"
