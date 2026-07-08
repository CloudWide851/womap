from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.features.exports.router import get_export_service
from app.features.exports.schemas import ExportFormat
from app.features.exports.service import (
    ExportDependencyError,
    ExportNoDataError,
    ExportRequestError,
)
from app.features.exports.writer import ExportArchive, build_shapefile_field_mapping, unique_dataset_name
from app.main import create_app


class FakeExportService:
    def __init__(self, archive: ExportArchive | None = None, error: Exception | None = None) -> None:
        self.archive = archive
        self.error = error
        self.calls: list[tuple[ExportFormat, list[int]]] = []

    async def export_layers(self, export_format: ExportFormat, layer_ids: list[int]) -> ExportArchive:
        self.calls.append((export_format, layer_ids))
        if self.error is not None:
            raise self.error
        if self.archive is None:
            raise AssertionError("fake archive is required")
        return self.archive


def build_client(service: FakeExportService) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_export_service] = lambda: service
    return TestClient(app)


def make_archive(tmp_path: Path) -> ExportArchive:
    root = tmp_path / "archive-root"
    root.mkdir()
    zip_path = root / "womap-export-shp.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("field-map.json", "{}")
    return ExportArchive(path=zip_path, cleanup_path=root, filename="womap-export-shp.zip")


def test_export_layers_returns_zip_archive(tmp_path: Path) -> None:
    service = FakeExportService(archive=make_archive(tmp_path))
    client = build_client(service)

    response = client.post("/api/v1/exports", json={"format": "shp", "layer_ids": [2, 1]})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert 'filename="womap-export-shp.zip"' in response.headers["content-disposition"]
    assert service.calls == [("shp", [2, 1])]
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        assert "field-map.json" in archive.namelist()


def test_export_layers_rejects_empty_layer_selection() -> None:
    service = FakeExportService(error=ExportRequestError("请至少选择一个后端图层。"))
    client = build_client(service)

    response = client.post("/api/v1/exports", json={"format": "shp", "layer_ids": []})

    assert response.status_code == 400
    assert response.json()["detail"] == "请至少选择一个后端图层。"


def test_export_layers_rejects_unknown_format() -> None:
    service = FakeExportService(archive=None)
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
