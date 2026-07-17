from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.features.exports.router import get_export_service
from app.features.exports.schemas import ExportFormat
from app.features.jobs.schemas import JobStatus, VectorExportJobProgressDetail
from app.features.exports.service import (
    ExportDependencyError,
    ExportNoDataError,
    ExportRequestError,
)
from app.features.exports.writer import ExportArchive, build_shapefile_field_mapping, unique_dataset_name
from app.main import create_app
from conftest import allow_test_auth


class FakeExportService:
    def __init__(
        self,
        job: JobStatus | None = None,
        error: Exception | None = None,
        download: tuple[Path, str] | None = None,
    ) -> None:
        self.job = job
        self.error = error
        self.download = download
        self.calls: list[tuple[ExportFormat, list[int]]] = []

    async def queue_export(self, export_format: ExportFormat, layer_ids: list[int]) -> JobStatus:
        self.calls.append((export_format, layer_ids))
        if self.error is not None:
            raise self.error
        if self.job is None:
            raise AssertionError("fake job is required")
        return self.job

    async def download_path(self, job_id: str) -> tuple[Path, str]:
        if self.error is not None:
            raise self.error
        if self.download is None:
            raise KeyError(job_id)
        return self.download


def build_client(service: FakeExportService) -> TestClient:
    app = allow_test_auth(create_app())
    app.dependency_overrides[get_export_service] = lambda: service
    return TestClient(app)


def make_archive(tmp_path: Path) -> ExportArchive:
    root = tmp_path / "archive-root"
    root.mkdir()
    zip_path = root / "womap-export-shp.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("field-map.json", "{}")
    return ExportArchive(path=zip_path, cleanup_path=root, filename="womap-export-shp.zip")


def queued_export_job() -> JobStatus:
    return JobStatus(
        id="vector-export-test",
        job_type="vector-export",
        status="queued",
        progress=0,
        message="矢量导出已进入队列。",
        detail=VectorExportJobProgressDetail(total_layers=2),
    )


def test_export_layers_queues_persistent_job() -> None:
    service = FakeExportService(job=queued_export_job())
    client = build_client(service)

    response = client.post("/api/v1/exports", json={"format": "shp", "layer_ids": [2, 1]})

    assert response.status_code == 202
    assert response.json()["job_type"] == "vector-export"
    assert response.json()["detail"]["kind"] == "vector-export"
    assert service.calls == [("shp", [2, 1])]


def test_download_vector_export_returns_completed_artifact(tmp_path: Path) -> None:
    archive = make_archive(tmp_path)
    service = FakeExportService(download=(archive.path, archive.filename))
    response = build_client(service).get("/api/v1/exports/vector-export-test/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert 'filename="womap-export-shp.zip"' in response.headers["content-disposition"]
    with zipfile.ZipFile(archive.path) as source:
        assert "field-map.json" in source.namelist()


def test_download_vector_export_rejects_unfinished_job() -> None:
    response = build_client(FakeExportService()).get(
        "/api/v1/exports/vector-export-test/download"
    )

    assert response.status_code == 404


def test_export_layers_rejects_empty_layer_selection() -> None:
    service = FakeExportService(error=ExportRequestError("请至少选择一个后端图层。"))
    client = build_client(service)

    response = client.post("/api/v1/exports", json={"format": "shp", "layer_ids": []})

    assert response.status_code == 400
    assert response.json()["detail"] == "请至少选择一个后端图层。"


def test_export_layers_rejects_unknown_format() -> None:
    service = FakeExportService()
    client = build_client(service)

    response = client.post("/api/v1/exports", json={"format": "geojson", "layer_ids": [1]})

    assert response.status_code == 422
    assert service.calls == []


def test_export_layers_reports_no_backend_data() -> None:
    service = FakeExportService(error=ExportNoDataError("没有找到可导出的后端图层或图斑。"))
    client = build_client(service)

    response = client.post("/api/v1/exports", json={"format": "gdb", "layer_ids": [1]})

    assert response.status_code == 404
    assert response.json()["detail"] == "没有找到可导出的后端图层或图斑。"


def test_export_layers_reports_missing_gdal_driver() -> None:
    service = FakeExportService(error=ExportDependencyError("缺少 pyogrio/GDAL，无法写出 SHP 或 GDB。"))
    client = build_client(service)

    response = client.post("/api/v1/exports", json={"format": "shp", "layer_ids": [1]})

    assert response.status_code == 501
    assert "GDAL" in response.json()["detail"]


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        (["project_code", "project-code"], {"project_code": "PROJECT_CO", "project-code": "PROJECT_C2"}),
        (["123long_field_name", "中文字段"], {"123long_field_name": "F_123LONG", "中文字段": "FIELD2"}),
    ],
)
def test_shapefile_field_mapping_uses_unique_ten_character_names(
    fields: list[str],
    expected: dict[str, str],
) -> None:
    mapping = build_shapefile_field_mapping(fields)

    assert mapping == expected
    assert all(len(short_name) <= 10 for short_name in mapping.values())
    assert len(set(mapping.values())) == len(fields)


def test_dataset_names_are_unique_and_ascii_safe() -> None:
    used: set[str] = set()

    assert unique_dataset_name("项目边界", used, fallback="layer_1") == "layer_1"
    assert unique_dataset_name("项目边界", used, fallback="layer_2") == "layer_2"
    assert unique_dataset_name("Layer A", used, fallback="layer_3") == "layer_a"
    assert unique_dataset_name("Layer A", used, fallback="layer_4") == "layer_a_2"
