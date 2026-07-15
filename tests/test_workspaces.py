from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.features.layers.repository import LayerRepository
from app.features.workspaces.package_io import (
    WorkspacePackageError,
    build_workspace_package,
    extract_geopackage,
    read_package_layer,
    validate_workspace_package,
)
from app.features.workspaces.schemas import (
    WorkspaceBasemapReference,
    WorkspaceCreate,
    WorkspaceDetail,
    WorkspaceFeatureSelection,
    WorkspaceLayerConfig,
    WorkspaceLayerState,
    WorkspaceMapView,
    WorkspacePackageManifest,
    WorkspaceUpdate,
)
from app.features.workspaces.service import WorkspaceConflictError, WorkspaceService
from app.models.layer import Layer
from app.models.project import Project


def make_layer(layer_id: int = 1, *, dataset_id: str | None = "dataset-1") -> Layer:
    return Layer(
        id=layer_id,
        project_id=1,
        name=f"图层 {layer_id}",
        source_type="gdb" if dataset_id else "manual",
        geometry_type="Polygon",
        feature_count=2,
        crs="EPSG:3857",
        bounds={"min_x": 0, "min_y": 0, "max_x": 20, "max_y": 20},
        style={"color": "#4656a8"},
        fields=[{"name": "名称", "type": "string"}],
        performance={
            "source_id": "source-1",
            "dataset_id": dataset_id,
            "container": "sample.gdb",
            "fingerprint": "abc123",
        },
        data_path=None,
        visible=True,
        locked=False,
        opacity=0.8,
    )


class MemoryWorkspaceRepository:
    def __init__(self) -> None:
        self.layers = [make_layer()]
        self.projects = [
            Project(
                id=1,
                name="本地工作台",
                default_basemap="amap-vector",
                current_view={},
            )
        ]
        self.next_id = 2

    async def ensure_default(self):
        return self.projects[0]

    async def list_projects(self):
        return self.projects

    async def list_layers(self):
        return self.layers

    async def get_project(self, workspace_id: int):
        return next((item for item in self.projects if item.id == workspace_id), None)

    async def name_exists(self, name: str, exclude_id: int | None = None):
        return any(item.id != exclude_id and item.name.casefold() == name.casefold() for item in self.projects)

    async def create_project(self, *, name: str, default_basemap: str, current_view: dict):
        project = Project(
            id=self.next_id,
            name=name,
            default_basemap=default_basemap,
            current_view=current_view,
        )
        self.next_id += 1
        self.projects.append(project)
        return project

    async def save_project(self, project: Project):
        return project

    async def delete_project(self, project: Project):
        if project.name == "本地工作台":
            raise ValueError("默认工作空间不能删除。")
        self.projects.remove(project)


@pytest.mark.asyncio
async def test_workspace_crud_revision_and_dataset_rebind() -> None:
    repository = MemoryWorkspaceRepository()
    service = WorkspaceService(repository)  # type: ignore[arg-type]
    created = await service.create_workspace(
        WorkspaceCreate(
            name="规划核查",
            description="指定数据上下文",
            default_basemap="amap-vector",
            layers=[
                WorkspaceLayerConfig(
                    layer_id=1,
                    dataset_id="dataset-1",
                    selection=WorkspaceFeatureSelection(mode="include", source_feature_ids=["A-1"]),
                )
            ],
        )
    )
    assert created.revision == 1
    assert created.layers[0].config.selection.source_feature_ids == ["A-1"]

    repository.layers = [make_layer(9)]
    rebound = await service.get_workspace(created.id)
    assert rebound.layers[0].layer.id == 9
    assert rebound.layers[0].config.layer_id == 9

    with pytest.raises(WorkspaceConflictError, match="其他窗口"):
        await service.update_workspace(
            created.id,
            WorkspaceUpdate(
                name="规划核查",
                revision=99,
                default_basemap="amap-vector",
                layers=[],
            ),
        )

    await service.delete_workspace(created.id)
    assert [project.name for project in repository.projects] == ["本地工作台"]
    assert repository.layers[0].id == 9


@pytest.mark.asyncio
async def test_default_workspace_includes_layers_but_legacy_named_workspace_does_not() -> None:
    repository = MemoryWorkspaceRepository()
    repository.projects.append(
        Project(id=2, name="旧项目", default_basemap="osm", current_view={})
    )
    service = WorkspaceService(repository)  # type: ignore[arg-type]
    default = await service.get_workspace(1)
    legacy = await service.get_workspace(2)
    assert [state.layer.id for state in default.layers] == [1]
    assert legacy.layers == []


def test_workspace_required_text_rejects_whitespace() -> None:
    with pytest.raises(ValidationError):
        WorkspaceCreate(name="   ", default_basemap="osm")
    with pytest.raises(ValidationError):
        WorkspaceCreate(name="工作空间", default_basemap="   ")


def make_workspace_detail() -> WorkspaceDetail:
    layer = make_layer()
    config = WorkspaceLayerConfig(layer_id=1, dataset_id="dataset-1")
    return WorkspaceDetail(
        id=3,
        name="测试工作空间",
        description="往返验证",
        default_basemap="amap-vector",
        revision=2,
        layer_count=1,
        workspace_uuid="11111111-1111-1111-1111-111111111111",
        view=WorkspaceMapView(center=(0, 0), zoom=12),
        layers=[WorkspaceLayerState(config=config, layer=LayerRepository.to_summary(layer))],
    )


def test_workspace_package_geopackage_subset_round_trip(tmp_path: Path) -> None:
    workspace = make_workspace_detail()
    archive = build_workspace_package(
        output_dir=tmp_path / "artifacts",
        workspace=workspace,
        basemap=WorkspaceBasemapReference(id="amap-vector", name="高德矢量", type="xyz"),
        layer_features={
            1: [
                {
                    "id": 10,
                    "source_feature_id": "source-10",
                    "properties": {"名称": "一号地块", "嵌套": {"等级": 2}},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 0], [20, 0], [20, 20], [0, 0]]],
                    },
                }
            ]
        },
    )
    validated = validate_workspace_package(archive.path)
    gpkg = extract_geopackage(validated, tmp_path / "extract")
    rows = read_package_layer(gpkg, validated.manifest.layers[0])
    assert archive.filename.endswith(".womap.zip")
    assert len(rows) == 1
    assert rows[0]["source_feature_id"] == "source-10"
    assert rows[0]["properties"]["名称"] == "一号地块"
    assert rows[0]["properties"]["嵌套"] == {"等级": 2}
    with zipfile.ZipFile(archive.path) as package:
        serialized = b"".join(package.read(name) for name in package.namelist())
    assert b"password" not in serialized.lower()
    assert b"api_key" not in serialized.lower()


def _write_minimal_package(path: Path, manifest: WorkspacePackageManifest) -> None:
    files = {
        "manifest.json": json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False).encode(),
        "data.gpkg": b"gpkg",
        "README.txt": b"WOMAP",
    }
    checksums = {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
        archive.writestr("checksums.json", json.dumps(checksums))


def minimal_manifest() -> WorkspacePackageManifest:
    return WorkspacePackageManifest(
        workspace_name="安全测试",
        workspace_uuid="22222222-2222-2222-2222-222222222222",
        revision=1,
        view=WorkspaceMapView(),
        basemap=WorkspaceBasemapReference(id="osm", name="OSM", type="xyz"),
        layers=[],
    )


def test_workspace_package_rejects_checksum_traversal_symlink_and_sensitive_manifest(
    tmp_path: Path,
) -> None:
    checksum_path = tmp_path / "checksum.womap.zip"
    _write_minimal_package(checksum_path, minimal_manifest())
    with zipfile.ZipFile(checksum_path, "a") as archive:
        archive.writestr("checksums.json", json.dumps({"manifest.json": "0" * 64}))
    with pytest.raises(WorkspacePackageError, match="重复文件名|校验"):
        validate_workspace_package(checksum_path)

    traversal_path = tmp_path / "traversal.womap.zip"
    with zipfile.ZipFile(traversal_path, "w") as archive:
        archive.writestr("../manifest.json", "{}")
    with pytest.raises(WorkspacePackageError, match="路径"):
        validate_workspace_package(traversal_path)

    symlink_path = tmp_path / "symlink.womap.zip"
    with zipfile.ZipFile(symlink_path, "w") as archive:
        info = zipfile.ZipInfo("manifest.json")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "data.gpkg")
        for name in ("data.gpkg", "checksums.json", "README.txt"):
            archive.writestr(name, b"")
    with pytest.raises(WorkspacePackageError, match="符号链接"):
        validate_workspace_package(symlink_path)

    sensitive = minimal_manifest().model_copy(
        update={"description": "password=secret"}
    )
    sensitive_path = tmp_path / "sensitive.womap.zip"
    _write_minimal_package(sensitive_path, sensitive)
    with pytest.raises(WorkspacePackageError, match="敏感"):
        validate_workspace_package(sensitive_path)


def test_workspace_package_rejects_abnormal_compression_ratio(tmp_path: Path) -> None:
    path = tmp_path / "bomb.womap.zip"
    manifest = minimal_manifest()
    manifest_bytes = json.dumps(manifest.model_dump(mode="json")).encode()
    readme = b"WOMAP"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", manifest_bytes)
        with archive.open("data.gpkg", "w") as target:
            block = b"0" * 1024 * 1024
            for _ in range(101):
                target.write(block)
        archive.writestr("README.txt", readme)
        archive.writestr(
            "checksums.json",
            json.dumps(
                {
                    "manifest.json": hashlib.sha256(manifest_bytes).hexdigest(),
                    "data.gpkg": "0" * 64,
                    "README.txt": hashlib.sha256(readme).hexdigest(),
                }
            ),
        )
    with pytest.raises(WorkspacePackageError, match="ZIP bomb"):
        validate_workspace_package(path)
