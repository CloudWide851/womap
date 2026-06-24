from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_service_status() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_placeholder_api_routes_are_available() -> None:
    client = TestClient(create_app())

    assert client.get("/api/v1/projects").json() == []
    assert client.get("/api/v1/layers").json() == []
