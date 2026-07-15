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
from conftest import allow_test_auth


class EmptyMapFeatureRepository(MapFeatureRepository):
    async def list_viewport_features(self, **kwargs):
        _ = kwargs
        return [], None, False


def create_api_test_app():
    app = allow_test_auth(create_app())
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
    assert body == {"status": "alive"}
    assert response.headers["x-request-id"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_liveness_probe_does_not_expose_runtime_configuration() -> None:
    response = TestClient(create_app()).get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    assert "database" not in response.text
    assert "config" not in response.text


def test_placeholder_api_routes_are_available() -> None:
    client = TestClient(create_api_test_app())

    assert client.get("/api/v1/projects").json() == []
    assert client.get("/api/v1/layers").json() == []


def test_basemaps_api_returns_enabled_providers() -> None:
    client = TestClient(allow_test_auth(create_app()))

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
    assert response.json()["request_id"] == response.headers["x-request-id"]


def test_validation_error_does_not_echo_rejected_input() -> None:
    client = TestClient(create_app())
    rejected_value = "should-never-be-returned"

    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": "local-admin",
            "password": "long-enough-local-password",
            "session_mode": rejected_value,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "请求参数无效。"
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert rejected_value not in response.text


def test_unhandled_error_is_redacted_and_correlated() -> None:
    app = create_app()
    private_message = "private-diagnostic-value"

    @app.get("/test/unhandled")
    async def unhandled() -> None:
        raise RuntimeError(private_message)

    response = TestClient(app, raise_server_exceptions=False).get("/test/unhandled")

    assert response.status_code == 500
    assert response.json()["detail"] == "服务处理请求时发生错误。"
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert private_message not in response.text


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
    client = TestClient(allow_test_auth(create_app()))

    response = client.get("/api/v1/settings/runtime")

    assert response.status_code == 200
    body = response.json()
    assert body["config_source"] in {"local", "example"}
    assert body["database"] == "postgresql"
    assert body["postgis_target"] is True
    assert body["performance"]["max_features_per_request"] == 5000
    assert body["auth"]["password_min_length"] >= 15
    assert body["auth"]["policy_refresh_seconds"] > 0
    assert body["panel_defaults"]["performance"] is True
