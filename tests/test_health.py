from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_service_status() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "postgresql"
    assert body["postgis_target"] is True
    assert body["redis_configured"] is True


def test_placeholder_api_routes_are_available() -> None:
    client = TestClient(create_app())

    assert client.get("/api/v1/projects").json() == []
    assert client.get("/api/v1/layers").json() == []


def test_basemaps_api_returns_enabled_providers() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/basemaps")

    assert response.status_code == 200
    body = response.json()
    assert {provider["id"] for provider in body} >= {"amap-vector", "tencent-vector"}
    assert all(provider["enabled"] for provider in body)


def test_feature_query_rejects_invalid_bbox() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/layers/1/features?bbox=1,2,0,4")

    assert response.status_code == 400


def test_feature_query_clamps_large_limit() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/layers/1/features?bbox=0,0,10,10&limit=999999")

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert body["meta"]["limit"] == 5000
    assert body["meta"]["truncated"] is True


def test_job_status_placeholder_route() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/jobs/import-1")

    assert response.status_code == 200
    assert response.json()["id"] == "import-1"
