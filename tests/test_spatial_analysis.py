from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.features.jobs.schemas import JobStatus, SpatialAnalysisJobProgressDetail
from app.features.spatial_analyses.router import get_spatial_analysis_service
from app.features.spatial_analyses.schemas import (
    SpatialAnalysisCreate,
    SpatialAnalysisHitPage,
    SpatialAnalysisResult,
)
from app.main import create_app


def analysis_job(status: str = "queued") -> JobStatus:
    return JobStatus(
        id="spatial-analysis-test",
        job_type="spatial-analysis",
        status=status,
        progress=0 if status == "queued" else 100,
        message="空间分析",
        detail=SpatialAnalysisJobProgressDetail(workspace_id=1, target_feature_id=2),
    )


class FakeSpatialAnalysisService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def queue(self, payload):
        if self.error:
            raise self.error
        assert payload.distance_meters == 1000
        return analysis_job()

    async def get_result(self, job_id: str):
        if self.error:
            raise self.error
        return SpatialAnalysisResult(
            job=analysis_job("done"),
            workspace_id=1,
            target_layer_id=1,
            target_feature_id=2,
            distance=1,
            unit="km",
            distance_meters=1000,
            scope="all",
        )

    async def hits(self, job_id: str, **kwargs):
        if self.error:
            raise self.error
        return SpatialAnalysisHitPage()

    async def cancel(self, job_id: str):
        if self.error:
            raise self.error
        return analysis_job("interrupted")

    async def queue_export(self, job_id: str):
        if self.error:
            raise self.error
        return JobStatus(
            id="spatial-analysis-export-test",
            job_type="spatial-analysis-export",
            status="queued",
            detail=SpatialAnalysisJobProgressDetail(),
        )


def analysis_client(service, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_spatial_analysis_service] = lambda: service

    async def no_background_job(_: str) -> None:
        return None

    monkeypatch.setattr(
        "app.features.spatial_analyses.router.execute_spatial_analysis_job",
        no_background_job,
    )
    monkeypatch.setattr(
        "app.features.spatial_analyses.router.execute_spatial_analysis_export_job",
        no_background_job,
    )
    return TestClient(app)


def test_analysis_units_are_normalized_to_meters() -> None:
    assert SpatialAnalysisCreate(
        workspace_id=1,
        target_layer_id=1,
        target_feature_id=1,
        distance=1,
        unit="km",
    ).distance_meters == 1000
    assert SpatialAnalysisCreate(
        workspace_id=1,
        target_layer_id=1,
        target_feature_id=1,
        distance=1,
        unit="ft",
    ).distance_meters == pytest.approx(0.3048)
    assert SpatialAnalysisCreate(
        workspace_id=1,
        target_layer_id=1,
        target_feature_id=1,
        distance=1,
        unit="mi",
    ).distance_meters == pytest.approx(1609.344)


def test_spatial_analysis_api_submit_result_hits_cancel_and_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = analysis_client(FakeSpatialAnalysisService(), monkeypatch)
    response = client.post(
        "/api/v1/spatial-analyses",
        json={
            "workspace_id": 1,
            "target_layer_id": 1,
            "target_feature_id": 2,
            "distance": 1,
            "unit": "km",
            "scope": "all",
        },
    )
    assert response.status_code == 202
    assert response.json()["detail"]["kind"] == "spatial-analysis"
    assert client.get("/api/v1/spatial-analyses/spatial-analysis-test").status_code == 200
    assert client.get("/api/v1/spatial-analyses/spatial-analysis-test/hits").json()["items"] == []
    assert client.post("/api/v1/spatial-analyses/spatial-analysis-test/cancel").status_code == 200
    assert client.post("/api/v1/spatial-analyses/spatial-analysis-test/exports").status_code == 202


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (KeyError("missing"), 404),
        (ValueError("bad"), 400),
        (RuntimeError("busy"), 409),
    ],
)
def test_spatial_analysis_api_error_mapping(
    error: Exception,
    expected: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = analysis_client(FakeSpatialAnalysisService(error), monkeypatch)
    response = client.post(
        "/api/v1/spatial-analyses",
        json={
            "workspace_id": 1,
            "target_layer_id": 1,
            "target_feature_id": 2,
            "distance": 10,
            "unit": "m",
        },
    )
    assert response.status_code == expected
