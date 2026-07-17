from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.shared import frontend_runtime
from app.shared.config import load_settings


def _production_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text(
        '<!doctype html><main id="root">production-index</main>',
        encoding="utf-8",
    )
    (assets / "app-abcdef12.js").write_text("window.WOMAP = true;", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg></svg>", encoding="utf-8")
    settings = load_settings()
    settings.runtime.mode = "production"
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(frontend_runtime, "FRONTEND_DIST", dist)
    return main_module.create_app()


def test_production_serves_spa_routes_with_revalidatable_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(_production_app(tmp_path, monkeypatch))

    root = client.get("/")
    nested = client.get("/workspaces/local/overview")

    assert root.status_code == 200
    assert nested.status_code == 200
    assert root.text == nested.text
    assert "production-index" in root.text
    assert root.headers["cache-control"] == "no-cache"
    assert nested.headers["cache-control"] == "no-cache"


def test_production_hash_assets_are_immutable_and_other_files_revalidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(_production_app(tmp_path, monkeypatch))

    hashed = client.get("/assets/app-abcdef12.js")
    plain = client.get("/favicon.svg")

    assert hashed.status_code == 200
    assert hashed.text == "window.WOMAP = true;"
    assert hashed.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert plain.status_code == 200
    assert plain.headers["cache-control"] == "public, max-age=3600, must-revalidate"


@pytest.mark.parametrize(
    "path",
    (
        "/api/v1/not-a-real-route",
        "/health/not-a-real-probe",
        "/assets/missing-abcdef12.js",
    ),
)
def test_production_reserved_or_missing_resources_return_json_404_not_spa(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    client = TestClient(_production_app(tmp_path, monkeypatch))

    response = client.get(path)

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert "production-index" not in response.text
    assert response.json()["request_id"] == response.headers["x-request-id"]


def test_production_requires_a_completed_frontend_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings()
    settings.runtime.mode = "production"
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(frontend_runtime, "FRONTEND_DIST", tmp_path / "missing-dist")

    with pytest.raises(RuntimeError, match="production frontend build is missing"):
        main_module.create_app()
