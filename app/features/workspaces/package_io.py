from __future__ import annotations

import hashlib
import hmac
import json
import re
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import ValidationError

from app.features.exports.writer import unique_dataset_name
from app.features.workspaces.schemas import (
    WorkspaceBasemapReference,
    WorkspaceDetail,
    WorkspacePackageLayerManifest,
    WorkspacePackageManifest,
)

MAX_ARCHIVE_ENTRIES = 1024
MAX_COMPRESSED_BYTES = 2 * 1024**3
MAX_UNCOMPRESSED_BYTES = 10 * 1024**3
REQUIRED_MEMBERS = {"manifest.json", "data.gpkg", "checksums.json", "README.txt"}
RESERVED_FIELDS = {"womap_feature_id", "womap_source_feature_id", "geometry"}


class WorkspacePackageError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedWorkspacePackage:
    path: Path
    manifest: WorkspacePackageManifest


@dataclass(frozen=True)
class WorkspacePackageArchive:
    path: Path
    filename: str
    manifest: WorkspacePackageManifest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _safe_archive_name(name: str) -> None:
    if not name or "\\" in name or name.startswith(("/", "\\")):
        raise WorkspacePackageError("工作空间包包含非法路径。")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or any(":" in part for part in path.parts):
        raise WorkspacePackageError("工作空间包包含路径穿越或绝对路径。")
    if len(path.parts) != 1:
        raise WorkspacePackageError("工作空间包只能包含约定的根目录文件。")


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK


def _assert_no_sensitive_manifest_data(manifest: WorkspacePackageManifest) -> None:
    encoded = json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False).lower()
    forbidden = (
        "password",
        "api_key",
        "apikey",
        "session_id",
        "credential",
        "file://",
        "smb://",
        "\\\\",
    )
    if any(token in encoded for token in forbidden):
        raise WorkspacePackageError("工作空间包清单包含路径、凭据或会话等敏感信息。")
    if re.search(r"(?:[a-z]:[/\\]|/(?:users|home|var|etc)/)", encoded, re.IGNORECASE):
        raise WorkspacePackageError("工作空间包清单包含本地绝对路径。")


def validate_workspace_package(path: Path) -> ValidatedWorkspacePackage:
    if not path.is_file() or path.stat().st_size > MAX_COMPRESSED_BYTES:
        raise WorkspacePackageError("工作空间包不存在或压缩体积超过 2 GiB。")
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise WorkspacePackageError("上传文件不是有效的 WOMAP ZIP 包。") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_ENTRIES:
            raise WorkspacePackageError("工作空间包条目数超过 1024。")
        names: set[str] = set()
        compressed_size = 0
        uncompressed_size = 0
        for info in infos:
            _safe_archive_name(info.filename)
            if info.filename in names:
                raise WorkspacePackageError("工作空间包包含重复文件名。")
            names.add(info.filename)
            if _is_symlink(info):
                raise WorkspacePackageError("工作空间包不允许包含符号链接。")
            if info.flag_bits & 0x1:
                raise WorkspacePackageError("工作空间包不允许使用加密条目。")
            compressed_size += info.compress_size
            uncompressed_size += info.file_size
            if (
                info.file_size > 100 * 1024**2
                and info.file_size / max(1, info.compress_size) > 200
            ):
                raise WorkspacePackageError("工作空间包压缩比异常，疑似 ZIP bomb。")
        if compressed_size > MAX_COMPRESSED_BYTES:
            raise WorkspacePackageError("工作空间包压缩体积超过 2 GiB。")
        if uncompressed_size > MAX_UNCOMPRESSED_BYTES:
            raise WorkspacePackageError("工作空间包解压体积超过 10 GiB。")
        if names != REQUIRED_MEMBERS:
            missing = sorted(REQUIRED_MEMBERS - names)
            unexpected = sorted(names - REQUIRED_MEMBERS)
            detail = "、".join([*(f"缺少 {name}" for name in missing), *(f"未知 {name}" for name in unexpected)])
            raise WorkspacePackageError(f"工作空间包结构不完整：{detail}。")
        free_bytes = shutil.disk_usage(path.parent).free
        if free_bytes < uncompressed_size + 128 * 1024**2:
            raise WorkspacePackageError("磁盘空间不足，无法安全预览工作空间包。")
        try:
            checksums = json.loads(archive.read("checksums.json"))
            manifest_raw = archive.read("manifest.json")
            manifest = WorkspacePackageManifest.model_validate_json(manifest_raw)
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
            raise WorkspacePackageError("工作空间包清单或校验文件无效。") from exc
        if not isinstance(checksums, dict):
            raise WorkspacePackageError("工作空间包校验文件格式无效。")
        for member in ("manifest.json", "data.gpkg", "README.txt"):
            expected = checksums.get(member)
            if not isinstance(expected, str) or len(expected) != 64:
                raise WorkspacePackageError(f"工作空间包缺少 {member} 的 SHA-256 校验值。")
            actual = hashlib.sha256(archive.read(member)).hexdigest()
            if not hmac.compare_digest(actual, expected.lower()):
                raise WorkspacePackageError(f"工作空间包 {member} 校验失败。")
        _assert_no_sensitive_manifest_data(manifest)
    return ValidatedWorkspacePackage(path=path, manifest=manifest)


def extract_geopackage(package: ValidatedWorkspacePackage, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = (target_dir / "data.gpkg").resolve()
    if target.parent != target_dir.resolve():
        raise WorkspacePackageError("工作空间包解压路径无效。")
    with zipfile.ZipFile(package.path) as archive, archive.open("data.gpkg") as source:
        with target.open("wb") as destination:
            shutil.copyfileobj(source, destination, length=1024 * 1024)
    return target


def build_workspace_package(
    *,
    output_dir: Path,
    workspace: WorkspaceDetail,
    basemap: WorkspaceBasemapReference,
    layer_features: dict[int, list[dict[str, Any]]],
) -> WorkspacePackageArchive:
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="womap-package-", dir=output_dir))
    gpkg_path = temporary / "data.gpkg"
    manifest_layers: list[WorkspacePackageLayerManifest] = []
    used_layer_names: set[str] = set()
    wrote_layer = False
    try:
        for state in workspace.layers:
            features = layer_features.get(state.layer.id, [])
            package_layer = unique_dataset_name(
                state.layer.name,
                used_layer_names,
                fallback=f"layer_{state.layer.id}",
            )
            field_mapping = _field_mapping(features)
            if features:
                _write_geopackage_layer(
                    gpkg_path,
                    package_layer,
                    state.layer.crs or "EPSG:3857",
                    features,
                    field_mapping,
                    append=wrote_layer,
                )
                wrote_layer = True
            provenance = state.layer.provenance
            manifest_layers.append(
                WorkspacePackageLayerManifest(
                    package_layer=package_layer,
                    original_layer_id=state.layer.id,
                    name=state.layer.name,
                    geometry_type=state.layer.geometry_type,
                    crs=state.layer.crs or "EPSG:3857",
                    source_type=state.layer.source_type,
                    feature_count=len(features),
                    fields=state.layer.fields,
                    field_mapping=field_mapping,
                    source_id=provenance.source_id,
                    dataset_id=provenance.dataset_id,
                    container=Path(provenance.container).name if provenance.container else None,
                    fingerprint=provenance.fingerprint,
                    config=state.config,
                )
            )
        if not wrote_layer:
            _create_empty_geopackage(gpkg_path)
        manifest = WorkspacePackageManifest(
            workspace_name=workspace.name,
            workspace_uuid=workspace.workspace_uuid,
            revision=workspace.revision,
            description=workspace.description,
            view=workspace.view,
            basemap=basemap,
            layers=manifest_layers,
        )
        _assert_no_sensitive_manifest_data(manifest)
        manifest_path = temporary / "manifest.json"
        readme_path = temporary / "README.txt"
        manifest_path.write_bytes(_json_bytes(manifest.model_dump(mode="json")))
        readme_path.write_text(
            "WOMAP 可移植工作空间包\n"
            "包含工作空间选中的矢量图层和图斑；不包含在线底图瓦片、凭据或本地路径。\n",
            encoding="utf-8",
        )
        checksums = {
            "manifest.json": _sha256(manifest_path),
            "data.gpkg": _sha256(gpkg_path),
            "README.txt": _sha256(readme_path),
        }
        (temporary / "checksums.json").write_bytes(_json_bytes(checksums))
        safe_name = re.sub(r"[^0-9A-Za-z_-]+", "-", workspace.name).strip("-") or "workspace"
        filename = f"{safe_name[:60]}.womap.zip"
        destination = output_dir / filename
        counter = 1
        while destination.exists():
            counter += 1
            destination = output_dir / f"{safe_name[:54]}-{counter}.womap.zip"
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for member in sorted(REQUIRED_MEMBERS):
                archive.write(temporary / member, arcname=member)
        validate_workspace_package(destination)
        return WorkspacePackageArchive(path=destination, filename=destination.name, manifest=manifest)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def read_package_layer(
    gpkg_path: Path,
    layer: WorkspacePackageLayerManifest,
) -> list[dict[str, Any]]:
    if layer.feature_count == 0:
        return []
    try:
        import pyogrio
    except Exception as exc:  # pragma: no cover - dependency gate
        raise WorkspacePackageError("缺少 pyogrio/GDAL，无法读取 GeoPackage。") from exc
    try:
        dataframe = pyogrio.read_dataframe(gpkg_path, layer=layer.package_layer)
    except Exception as exc:
        raise WorkspacePackageError(f"GeoPackage 图层 {layer.name} 读取失败：{exc}") from exc
    if len(dataframe.index) != layer.feature_count:
        raise WorkspacePackageError(f"GeoPackage 图层 {layer.name} 的图斑数与清单不一致。")
    if dataframe.crs is None:
        raise WorkspacePackageError(f"GeoPackage 图层 {layer.name} 缺少 CRS。")
    if dataframe.crs.to_epsg() != 3857:
        dataframe = dataframe.to_crs("EPSG:3857")
    reverse_fields = {package: original for original, package in layer.field_mapping.items()}
    rows: list[dict[str, Any]] = []
    for _, record in dataframe.iterrows():
        geometry = record.get("geometry")
        if geometry is None or geometry.is_empty:
            raise WorkspacePackageError(f"GeoPackage 图层 {layer.name} 包含空几何。")
        properties: dict[str, Any] = {}
        for package_field, original in reverse_fields.items():
            value = record.get(package_field)
            if _is_missing(value):
                value = None
            elif isinstance(value, str) and value.startswith("__womap_json__:"):
                value = json.loads(value.removeprefix("__womap_json__:"))
            elif hasattr(value, "item"):
                value = value.item()
            properties[original] = value
        source_feature_id = record.get("womap_source_feature_id")
        if _is_missing(source_feature_id):
            source_feature_id = None
        rows.append(
            {
                "source_feature_id": str(source_feature_id) if source_feature_id is not None else None,
                "geometry": geometry,
                "properties": properties,
            }
        )
    return rows


def _field_mapping(features: list[dict[str, Any]]) -> dict[str, str]:
    names = sorted({str(key) for feature in features for key in feature["properties"]})
    mapping: dict[str, str] = {}
    used = {field.casefold() for field in RESERVED_FIELDS}
    for index, original in enumerate(names, start=1):
        candidate = original.strip()
        if not candidate or candidate.casefold() in used or len(candidate) > 60:
            candidate = f"field_{index}"
        base = candidate
        suffix = 1
        while candidate.casefold() in used:
            suffix += 1
            candidate = f"{base[: 54]}_{suffix}"
        used.add(candidate.casefold())
        mapping[original] = candidate
    return mapping


def _write_geopackage_layer(
    path: Path,
    layer_name: str,
    crs: str,
    features: list[dict[str, Any]],
    field_mapping: dict[str, str],
    *,
    append: bool,
) -> None:
    try:
        import geopandas as gpd
        import pyogrio
        from shapely.geometry import shape
    except Exception as exc:  # pragma: no cover - dependency gate
        raise WorkspacePackageError("缺少 geopandas/pyogrio，无法写出 GeoPackage。") from exc
    records: list[dict[str, Any]] = []
    geometries = []
    for feature in features:
        record: dict[str, Any] = {
            "womap_feature_id": feature["id"],
            "womap_source_feature_id": feature["source_feature_id"],
        }
        for original, package_field in field_mapping.items():
            record[package_field] = _portable_value(feature["properties"].get(original))
        records.append(record)
        geometries.append(shape(feature["geometry"]))
    dataframe = gpd.GeoDataFrame(records, geometry=geometries, crs=crs)
    pyogrio.write_dataframe(dataframe, path, driver="GPKG", layer=layer_name, append=append)


def _portable_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return "__womap_json__:" + json.dumps(value, ensure_ascii=False, sort_keys=True)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(value != value)
    except Exception:
        return False


def _create_empty_geopackage(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            PRAGMA application_id = 1196437808;
            PRAGMA user_version = 10200;
            CREATE TABLE gpkg_spatial_ref_sys (
              srs_name TEXT NOT NULL, srs_id INTEGER NOT NULL PRIMARY KEY,
              organization TEXT NOT NULL, organization_coordsys_id INTEGER NOT NULL,
              definition TEXT NOT NULL, description TEXT
            );
            CREATE TABLE gpkg_contents (
              table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT NULL,
              identifier TEXT UNIQUE, description TEXT DEFAULT '', last_change DATETIME NOT NULL,
              min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE, srs_id INTEGER
            );
            CREATE TABLE gpkg_geometry_columns (
              table_name TEXT NOT NULL, column_name TEXT NOT NULL,
              geometry_type_name TEXT NOT NULL, srs_id INTEGER NOT NULL,
              z TINYINT NOT NULL, m TINYINT NOT NULL,
              PRIMARY KEY (table_name, column_name)
            );
            INSERT INTO gpkg_spatial_ref_sys VALUES
              ('Undefined Cartesian', -1, 'NONE', -1, 'undefined', 'undefined Cartesian coordinate reference system'),
              ('Undefined Geographic', 0, 'NONE', 0, 'undefined', 'undefined geographic coordinate reference system'),
              ('WGS 84 geodetic', 4326, 'EPSG', 4326, 'GEOGCS["WGS 84"]', 'longitude/latitude coordinates in decimal degrees on the WGS 84 spheroid');
            """
        )
