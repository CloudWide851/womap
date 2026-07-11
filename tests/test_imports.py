from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import geopandas as gpd
import pytest
import yaml
from shapely.geometry import Point

from app.features.imports.scanner import SHP_OPTIONAL, VectorDatasetScanner
from app.features.imports.repository import ImportRepository
from app.features.imports.schemas import CatalogDataset
from app.features.imports.service import ImportService
from app.features.imports.sources import SourceMaterializer, TransferProgress
from app.features.jobs.schemas import JobProgressDetail
from app.features.settings.schemas import (
    ImportSourceCreate,
    ImportSourceResponse,
    ImportSourceUpdate,
)
from app.features.settings.service import SettingsService
from app.models.job import Job
from app.models.layer import Layer


class MemoryCredentialStore:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, source_id: str, username: str) -> str | None:
        return self.values.get((source_id, username))

    def set_password(self, source_id: str, username: str, password: str) -> None:
        self.values[(source_id, username)] = password

    def delete_password(self, source_id: str, username: str) -> None:
        self.values.pop((source_id, username), None)


def test_shapefile_scanner_blocks_missing_core_files(tmp_path: Path) -> None:
    (tmp_path / "parcel.shp").write_bytes(b"placeholder")

    dataset = VectorDatasetScanner().scan("local", tmp_path).datasets[0]

    assert dataset.valid is False
    assert set(dataset.missing_required) == {".shx", ".dbf"}
    assert dataset.missing_optional == list(SHP_OPTIONAL)


def test_shapefile_scanner_reads_real_dataset_and_warns_for_optional_files(
    tmp_path: Path,
) -> None:
    dataframe = gpd.GeoDataFrame(
        {"name": ["A", "B"]},
        geometry=[Point(113.2, 23.1), Point(113.3, 23.2)],
        crs="EPSG:4326",
    )
    dataframe.to_file(tmp_path / "parcel.shp", driver="ESRI Shapefile", encoding="UTF-8")

    dataset = VectorDatasetScanner().scan("local", tmp_path).datasets[0]

    assert dataset.valid is True
    assert dataset.feature_count == 2
    assert dataset.crs
    assert dataset.geometry_type == "Point"
    assert ".sbn" in dataset.missing_optional
    assert dataset.fingerprint


def test_shapefile_scanner_accepts_arcgis_shp_xml_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for suffix in (".shp", ".shx", ".dbf"):
        (tmp_path / f"parcel{suffix}").write_bytes(b"data")
    (tmp_path / "parcel.shp.xml").write_text("<metadata />", encoding="utf-8")
    scanner = VectorDatasetScanner()
    monkeypatch.setattr(
        scanner,
        "_read_info",
        lambda *args, **kwargs: {
            "geometry_type": "Polygon",
            "features": 1,
            "crs": "EPSG:4326",
            "total_bounds": [1, 2, 3, 4],
        },
    )

    dataset = scanner.scan("local", tmp_path).datasets[0]

    assert dataset.valid is True
    assert ".xml" not in dataset.missing_optional


def test_gdb_scanner_lists_only_spatial_layers(tmp_path: Path, monkeypatch) -> None:
    gdb_path = tmp_path / "source.gdb"
    gdb_path.mkdir()
    (gdb_path / "a00000001.gdbtable").write_bytes(b"data")

    monkeypatch.setattr(
        "pyogrio.list_layers",
        lambda path: [("parcels", "Polygon"), ("codes", None)],
    )
    monkeypatch.setattr(
        "pyogrio.read_info",
        lambda *args, **kwargs: {
            "geometry_type": "Polygon",
            "features": 12,
            "crs": "EPSG:4490",
            "total_bounds": [1, 2, 3, 4],
            "fields": ["code"],
            "dtypes": ["object"],
        },
    )

    datasets = VectorDatasetScanner().scan("gdb-source", tmp_path).datasets

    assert [item.layer_name for item in datasets] == ["parcels"]
    assert datasets[0].feature_count == 12


@pytest.mark.asyncio
async def test_import_source_password_is_kept_out_of_yaml(tmp_path: Path) -> None:
    local_config = tmp_path / "settings.local.yaml"
    fallback = tmp_path / "settings.example.yaml"
    fallback.write_text("imports:\n  sources: []\n", encoding="utf-8")
    credentials = MemoryCredentialStore()
    service = SettingsService(local_config, fallback, credentials)

    source = await service.create_import_source(
        ImportSourceCreate(
            name="Remote",
            kind="smb",
            server="fileserver",
            share="gis",
            username="operator",
            password="secret-password",
        )
    )

    yaml_text = local_config.read_text(encoding="utf-8")
    assert "secret-password" not in yaml_text
    assert source.credential_configured is True
    assert credentials.get_password(source.id, "operator") == "secret-password"


@pytest.mark.asyncio
async def test_import_source_update_and_delete_are_persisted(tmp_path: Path) -> None:
    local_config = tmp_path / "settings.local.yaml"
    fallback = tmp_path / "settings.example.yaml"
    fallback.write_text("imports:\n  sources: []\n", encoding="utf-8")
    credentials = MemoryCredentialStore()
    service = SettingsService(local_config, fallback, credentials)
    source = await service.create_import_source(
        ImportSourceCreate(
            name="Remote",
            kind="smb",
            server="fileserver",
            share="gis",
            username="operator",
            password="old-password",
        )
    )

    updated = await service.update_import_source(
        source.id,
        ImportSourceUpdate(
            name="Updated remote",
            kind="smb",
            server="fileserver-2",
            share="maps",
            username="editor",
            password="new-password",
        ),
    )

    raw_config = yaml.safe_load(local_config.read_text(encoding="utf-8"))
    assert raw_config["imports"]["sources"] == [
        {
            "name": "Updated remote",
            "kind": "smb",
            "root_path": "",
            "server": "fileserver-2",
            "share": "maps",
            "base_path": "",
            "username": "editor",
            "domain": "",
            "port": 445,
            "encrypt": True,
            "enabled": True,
            "id": source.id,
        }
    ]
    assert updated.credential_configured is True
    assert credentials.get_password(source.id, "operator") is None
    assert credentials.get_password(source.id, "editor") == "new-password"

    await service.delete_import_source(source.id)

    raw_config = yaml.safe_load(local_config.read_text(encoding="utf-8"))
    assert raw_config["imports"]["sources"] == []
    assert credentials.get_password(source.id, "editor") is None


class FakeSmbClient:
    def __init__(self, content: bytes, mtime_ns: int) -> None:
        self.content = content
        self.mtime_ns = mtime_ns
        self.seek_offsets: list[int] = []

    def register_session(self, *args, **kwargs) -> None:
        _ = args, kwargs

    def walk(self, root: str):
        yield root, [], ["parcel.shp"]

    def stat(self, path: str):
        _ = path
        return SimpleNamespace(st_size=len(self.content), st_mtime_ns=self.mtime_ns)

    def open_file(self, path: str, mode: str):
        _ = path, mode
        client = self

        class TrackedBytesIO(io.BytesIO):
            def seek(self, offset: int, whence: int = 0) -> int:
                client.seek_offsets.append(offset)
                return super().seek(offset, whence)

        return TrackedBytesIO(self.content)


def _smb_source() -> ImportSourceResponse:
    return ImportSourceResponse(
        id="remote-source",
        name="Remote",
        kind="smb",
        server="fileserver",
        share="gis",
        username="operator",
        credential_configured=True,
    )


def test_smb_materializer_resumes_matching_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"abcdefghij"
    fake_smb = FakeSmbClient(content, mtime_ns=123)
    monkeypatch.setitem(sys.modules, "smbclient", fake_smb)
    credentials = MemoryCredentialStore()
    credentials.set_password("remote-source", "operator", "password")
    target_root = tmp_path / "remote-source" / "source"
    target_root.mkdir(parents=True)
    (target_root / "parcel.shp.part").write_bytes(content[:4])
    (target_root.parent / "transfer-manifest.json").write_text(
        json.dumps({"parcel.shp": {"size": len(content), "mtime_ns": 123}}),
        encoding="utf-8",
    )
    progress = TransferProgress()

    result = SourceMaterializer(credentials).materialize(_smb_source(), tmp_path, progress)

    assert fake_smb.seek_offsets == [4]
    assert (result / "parcel.shp").read_bytes() == content
    assert not (result / "parcel.shp.part").exists()
    assert progress.snapshot() == (len(content), len(content), "parcel.shp")


def test_smb_materializer_resets_partial_when_remote_file_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"new-content"
    fake_smb = FakeSmbClient(content, mtime_ns=456)
    monkeypatch.setitem(sys.modules, "smbclient", fake_smb)
    credentials = MemoryCredentialStore()
    credentials.set_password("remote-source", "operator", "password")
    target_root = tmp_path / "remote-source" / "source"
    target_root.mkdir(parents=True)
    (target_root / "parcel.shp.part").write_bytes(b"old")
    (target_root.parent / "transfer-manifest.json").write_text(
        json.dumps({"parcel.shp": {"size": len(content), "mtime_ns": 123}}),
        encoding="utf-8",
    )

    result = SourceMaterializer(credentials).materialize(_smb_source(), tmp_path)

    assert fake_smb.seek_offsets == [0]
    assert (result / "parcel.shp").read_bytes() == content


def test_smb_materializer_removes_files_deleted_from_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"current"
    fake_smb = FakeSmbClient(content, mtime_ns=456)
    monkeypatch.setitem(sys.modules, "smbclient", fake_smb)
    credentials = MemoryCredentialStore()
    credentials.set_password("remote-source", "operator", "password")
    target_root = tmp_path / "remote-source" / "source"
    target_root.mkdir(parents=True)
    (target_root / "deleted.shp").write_bytes(b"stale")
    (target_root.parent / "transfer-manifest.json").write_text(
        json.dumps({"deleted.shp": {"size": 5, "mtime_ns": 1}}),
        encoding="utf-8",
    )

    SourceMaterializer(credentials).materialize(_smb_source(), tmp_path)

    assert not (target_root / "deleted.shp").exists()
    manifest = json.loads((target_root.parent / "transfer-manifest.json").read_text("utf-8"))
    assert set(manifest) == {"parcel.shp"}


class ScalarResult:
    def __init__(self, values: list[Job]) -> None:
        self.values = values

    def all(self) -> list[Job]:
        return self.values


class ResumableSession:
    def __init__(self, jobs: list[Job]) -> None:
        self.jobs = jobs

    async def scalars(self, statement) -> ScalarResult:
        _ = statement
        return ScalarResult(self.jobs)


@pytest.mark.asyncio
async def test_completed_dataset_is_not_reported_as_resumable() -> None:
    job = Job(
        id="import-data-1",
        job_type="import-data",
        status="interrupted",
        progress=50,
        message="interrupted",
        payload={"source_id": "source-1", "dataset_ids": ["done", "pending"]},
        result={"completed_dataset_ids": ["done"]},
    )
    repository = ImportRepository(ResumableSession([job]))

    assert await repository.find_resumable_job("source-1", "done") is None
    assert await repository.find_resumable_job("source-1", "pending") is job


class BatchSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commits = 0

    def add_all(self, values: list[object]) -> None:
        self.added.extend(values)

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_batch_features_and_cursor_are_committed_together() -> None:
    session = BatchSession()
    repository = ImportRepository(session)
    layer = Layer(id=2, project_id=1, name="parcel", source_type="shp", geometry_type="Point", feature_count=0)
    job = Job(
        id="import-data-2",
        job_type="import-data",
        status="running",
        progress=0,
        message="running",
        payload={},
        result={},
    )
    detail = JobProgressDetail(
        stage="importing",
        current_layer="parcel",
        imported_features=1,
        total_features=2,
    )

    await repository.insert_batch(
        layer,
        job,
        [
            {
                "source_feature_id": "dataset:1",
                "geom": None,
                "properties": {"name": "A"},
                "bbox": {},
                "area": None,
                "perimeter": None,
                "revision": 1,
            }
        ],
        detail,
        {"offsets": {"dataset": 1}},
    )

    assert len(session.added) == 1
    assert layer.feature_count == 1
    assert job.result["offsets"] == {"dataset": 1}
    assert job.result["detail"]["imported_features"] == 1
    assert session.commits == 1


class FinalizeSession:
    def __init__(self) -> None:
        self.deleted: list[Layer] = []
        self.commits = 0

    async def delete(self, layer: Layer) -> None:
        self.deleted.append(layer)

    async def commit(self) -> None:
        self.commits += 1


class FinalizeRepository(ImportRepository):
    def __init__(self, session: FinalizeSession, old_layer: Layer) -> None:
        super().__init__(session)
        self.old_layer = old_layer

    async def imported_layers(self, source_id: str) -> list[Layer]:
        _ = source_id
        return [self.old_layer]


@pytest.mark.asyncio
async def test_staging_layer_replaces_old_layer_only_during_finalize() -> None:
    old_layer = Layer(
        id=1,
        project_id=1,
        name="parcel",
        source_type="shp",
        geometry_type="Point",
        feature_count=1,
        performance={"source_id": "source-1", "dataset_id": "dataset-1"},
        visible=True,
    )
    staging = Layer(
        id=2,
        project_id=1,
        name="parcel",
        source_type="shp",
        geometry_type="Point",
        feature_count=2,
        performance={"source_id": "source-1", "dataset_id": "dataset-1", "staging": True},
        visible=False,
    )
    dataset = CatalogDataset(
        id="dataset-1",
        source_id="source-1",
        format="shp",
        container=".",
        relative_path="parcel.shp",
        layer_name="parcel",
        fingerprint="new-fingerprint",
    )
    session = FinalizeSession()

    await FinalizeRepository(session, old_layer).finalize_layer(staging, dataset)

    assert session.deleted == [old_layer]
    assert staging.visible is True
    assert staging.performance["staging"] is False
    assert staging.performance["fingerprint"] == "new-fingerprint"
    assert session.commits == 1


class FailingRepository(ImportRepository):
    def __init__(self, job: Job) -> None:
        self.job = job
        self.rolled_back = False
        self.updated_after_rollback = False

    async def get_job(self, job_id: str) -> Job | None:
        return self.job if job_id == self.job.id else None

    async def rollback(self) -> None:
        self.rolled_back = True

    async def update_job(self, job: Job, **kwargs) -> None:
        assert self.rolled_back
        job.status = kwargs.get("status", job.status)
        job.message = kwargs.get("message", job.message)
        self.updated_after_rollback = True


@pytest.mark.asyncio
async def test_failed_import_rolls_back_before_marking_job_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = Job(
        id="import-data-3",
        job_type="import-data",
        status="running",
        progress=10,
        message="running",
        payload={"source_id": "source-1"},
        result={"detail": {"stage": "importing"}},
    )
    repository = FailingRepository(job)
    service = ImportService(repository)

    async def fail_import(current_job: Job) -> None:
        _ = current_job
        raise RuntimeError("database commit failed")

    monkeypatch.setattr(service, "_run_import", fail_import)

    await service.run_job(job.id)

    assert repository.rolled_back is True
    assert repository.updated_after_rollback is True
    assert job.status == "failed"


def test_import_feature_rows_are_json_safe_and_projected() -> None:
    dataframe = gpd.GeoDataFrame(
        {"name": ["A"], "nullable": [float("nan")]},
        geometry=[Point(12600000, 2640000)],
        crs="EPSG:3857",
    )
    dataset = CatalogDataset(
        id="dataset-1",
        source_id="source-1",
        format="shp",
        container=".",
        relative_path="parcel.shp",
        layer_name="parcel",
        fingerprint="abc",
    )

    rows = ImportService._feature_rows(dataframe, dataset)

    assert len(rows) == 1
    assert rows[0]["source_feature_id"] == "dataset-1:0"
    assert rows[0]["properties"] == {"name": "A", "nullable": None}
    assert json.dumps(rows[0]["properties"])
