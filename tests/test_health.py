from fastapi.testclient import TestClient

from app.main import create_app
from app.features.jobs.repository import JobRepository
from app.features.jobs.router import get_job_service
from app.features.jobs.service import JobService
from app.features.layers.repository import LayerRepository
from app.features.layers.router import get_layer_service
from app.features.layers.service import LayerService
from app.features.map_features.repository import MapFeatureRepository
from app.features.map_features.router import get_map_feature_service
from app.features.map_features.service import MapFeatureService


class EmptyMapFeatureRepository(MapFeatureRepository):
    async def list_viewport_features(self, **kwargs):
        _ = kwargs
        return [], None, False


def create_api_test_app():
    app = create_app()
    app.dependency_overrides[get_layer_service] = lambda: LayerService(LayerRepository())
    app.dependency_overrides[get_map_feature_service] = lambda: MapFeatureService(
        EmptyMapFeatureRepository()
    )
    app.dependency_overrides[get_job_service] = lambda: JobService(JobRepository())
    return app


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
    client = TestClient(create_api_test_app())

    assert client.get("/api/v1/projects").json() == []
    assert client.get("/api/v1/layers").json() == []


def test_basemaps_api_returns_enabled_providers() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/basemaps")

    assert response.status_code == 200
    body = response.json()
    assert {provider["id"] for provider in body} >= {"amap-vector", "tencent-vector"}
    assert all(provider["enabled"] for provider in body)


def test_auth_policy_api_returns_public_security_settings() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/auth/policy")

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["password_min_length"] >= 15
    assert body["password_max_length"] >= body["password_min_length"]
    assert body["idle_timeout_minutes"] > 0
    assert body["absolute_timeout_hours"] > 0
    assert body["secure_cookie"] is True
    assert body["http_only_cookie"] is True
    assert "password_hash" not in body


def test_login_rejects_password_outside_policy_before_secret_check() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/auth/login",
        json={"username": "local-admin", "password": "short", "session_mode": "short"},
    )

    assert response.status_code == 400


def test_feature_query_rejects_invalid_bbox() -> None:
    client = TestClient(create_api_test_app())

    response = client.get("/api/v1/layers/1/features?bbox=1,2,0,4")

    assert response.status_code == 400


def test_feature_query_clamps_large_limit() -> None:
    client = TestClient(create_api_test_app())

    response = client.get("/api/v1/layers/1/features?bbox=0,0,10,10&limit=999999")

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert body["meta"]["limit"] == 5000
    assert body["meta"]["truncated"] is True


def test_job_status_placeholder_route() -> None:
    client = TestClient(create_api_test_app())

    response = client.get("/api/v1/jobs/import-1")

    assert response.status_code == 200
    assert response.json()["id"] == "import-1"


def test_runtime_settings_api_uses_yaml_performance_config() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/settings/runtime")

    assert response.status_code == 200
    body = response.json()
    assert body["database"] == "postgresql"
    assert body["postgis_target"] is True
    assert body["performance"]["max_features_per_request"] == 5000
    assert body["auth"]["password_min_length"] >= 15
    assert body["auth"]["policy_refresh_seconds"] > 0
    assert body["panel_defaults"]["performance"] is True
