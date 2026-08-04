import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from kl_server.api.app import create_app


def test_health_rejects_without_token():
    client = TestClient(create_app(auth_token="s3cret"))
    assert client.get("/health").status_code == 401


def test_health_allows_with_token():
    client = TestClient(create_app(auth_token="s3cret"))
    response = client.get("/health", headers={"Authorization": "Bearer s3cret"})
    assert response.status_code == 200


def test_no_token_means_no_auth():
    client = TestClient(create_app())
    assert client.get("/health").status_code == 200


def test_health_rejects_wrong_token():
    client = TestClient(create_app(auth_token="s3cret"))
    response = client.get("/health", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


def test_websocket_rejects_without_token():
    client = TestClient(create_app(auth_token="s3cret"))
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/tasks/t1") as websocket:
            websocket.send_json({"event": "tool_result"})


def test_websocket_allows_with_token():
    client = TestClient(create_app(auth_token="s3cret"))
    with client.websocket_connect(
        "/ws/tasks/t1",
        headers={"Authorization": "Bearer s3cret"},
    ) as websocket:
        websocket.send_json({"event": "tool_result"})
        assert websocket.receive_json()["event"] == "tool_result"


def test_multiple_apps_have_isolated_tokens():
    client_a = TestClient(create_app(auth_token="token-a"))
    client_b = TestClient(create_app(auth_token="token-b"))
    assert client_a.get("/health", headers={"Authorization": "Bearer token-a"}).status_code == 200
    assert client_a.get("/health", headers={"Authorization": "Bearer token-b"}).status_code == 401
    assert client_b.get("/health", headers={"Authorization": "Bearer token-b"}).status_code == 200
