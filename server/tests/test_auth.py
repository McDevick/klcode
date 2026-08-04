from fastapi.testclient import TestClient

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
