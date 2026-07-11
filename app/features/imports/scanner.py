from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.features.imports.schemas import CatalogDataset, ImportCatalog

SHP_REQUIRED = (".shp", ".shx", ".dbf")
SHP_OPTIONAL = (".prj", ".cpg", ".sbn", ".sbx", ".xml")


class VectorDatasetScanner:
    def scan(self, source_id: str, root: Path) -> ImportCatalog:
        resolved_root = root.expanduser().resolve()
        if not resolved_root.is_dir():
            raise ValueError("数据源根目录不存在或不可访问。")

        datasets: list[CatalogDataset] = []
        gdb_paths: list[Path] = []
        for current, directory_names, file_names in os.walk(resolved_root):
            current_path = Path(current)
            gdb_directories = [name for name in directory_names if name.lower().endswith(".gdb")]
            for name in gdb_directories:
                gdb_paths.append(current_path / name)
            directory_names[:] = [name for name in directory_names if name not in gdb_directories]
            for file_name in file_names:
                if file_name.lower().endswith(".shp"):
                    datasets.append(self._scan_shapefile(source_id, resolved_root, current_path / file_name))

        for gdb_path in sorted(gdb_paths):
            datasets.extend(self._scan_gdb(source_id, resolved_root, gdb_path))

        return ImportCatalog(
            source_id=source_id,
            scanned_at=datetime.now(UTC).isoformat(),
            datasets=sorted(datasets, key=lambda item: (item.container.lower(), item.layer_name.lower())),
        )

    def _scan_shapefile(self, source_id: str, root: Path, shp_path: Path) -> CatalogDataset:
        sibling_map: dict[str, Path] = {}
        base_name = shp_path.stem.lower()
        metadata_name = f"{shp_path.name.lower()}.xml"
        for child in shp_path.parent.iterdir():
            suffix = child.suffix.lower()
            same_dataset = child.stem.lower() == base_name
            if child.is_file() and (same_dataset or child.name.lower() == metadata_name):
                sibling_map[suffix] = child
        missing_required = [suffix for suffix in SHP_REQUIRED if suffix not in sibling_map]
        missing_optional = [suffix for suffix in SHP_OPTIONAL if suffix not in sibling_map]
        relevant_files = [sibling_map[suffix] for suffix in sibling_map if suffix in SHP_REQUIRED + SHP_OPTIONAL]
        relative_path = shp_path.relative_to(root).as_posix()
        dataset_id = self._dataset_id(source_id, "shp", relative_path, shp_path.stem)
        geometry_type = "Unknown"
        feature_count = 0
        crs = None
        bounds: list[float] = []
        fields: list[dict[str, Any]] = []
        errors: list[str] = []

        if not missing_required:
            try:
                info = self._read_info(shp_path)
                geometry_type, feature_count, crs, bounds, fields = self._metadata(info)
            except Exception as exc:
                errors.append(f"无法读取 Shapefile：{exc}")

        return CatalogDataset(
            id=dataset_id,
            source_id=source_id,
            format="shp",
            container=shp_path.parent.relative_to(root).as_posix() or ".",
            relative_path=relative_path,
            layer_name=shp_path.stem,
            geometry_type=geometry_type,
            feature_count=feature_count,
            crs=crs,
            bounds=bounds,
            fields=fields,
            fingerprint=self._fingerprint(root, relevant_files),
            valid=not missing_required and not errors,
            missing_required=missing_required,
            missing_optional=missing_optional,
            errors=errors,
        )

    def _scan_gdb(self, source_id: str, root: Path, gdb_path: Path) -> list[CatalogDataset]:
        relative_path = gdb_path.relative_to(root).as_posix()
        fingerprint = self._fingerprint(root, [path for path in gdb_path.rglob("*") if path.is_file()])
        try:
            import pyogrio

            layers = pyogrio.list_layers(gdb_path)
        except Exception as exc:
            return [
                CatalogDataset(
                    id=self._dataset_id(source_id, "gdb", relative_path, gdb_path.stem),
                    source_id=source_id,
                    format="gdb",
                    container=relative_path,
                    relative_path=relative_path,
                    layer_name=gdb_path.stem,
                    fingerprint=fingerprint,
                    valid=False,
                    errors=[f"无法读取 FileGDB：{exc}"],
                )
            ]

        datasets: list[CatalogDataset] = []
        for layer_name, listed_geometry_type in layers:
            if listed_geometry_type is None:
                continue
            errors: list[str] = []
            try:
                info = self._read_info(gdb_path, layer=str(layer_name))
                geometry_type, feature_count, crs, bounds, fields = self._metadata(info)
            except Exception as exc:
                geometry_type = str(listed_geometry_type or "Unknown")
                feature_count = 0
                crs = None
                bounds = []
                fields = []
                errors.append(f"无法读取 GDB 图层：{exc}")
            datasets.append(
                CatalogDataset(
                    id=self._dataset_id(source_id, "gdb", relative_path, str(layer_name)),
                    source_id=source_id,
                    format="gdb",
                    container=relative_path,
                    relative_path=relative_path,
                    layer_name=str(layer_name),
                    geometry_type=geometry_type,
                    feature_count=feature_count,
                    crs=crs,
                    bounds=bounds,
                    fields=fields,
                    fingerprint=fingerprint,
                    valid=not errors,
                    errors=errors,
                )
            )
        return datasets

    @staticmethod
    def _read_info(path: Path, layer: str | None = None) -> dict[str, Any]:
        import pyogrio

        return pyogrio.read_info(path, layer=layer, force_feature_count=True, force_total_bounds=True)

    @staticmethod
    def _metadata(info: dict[str, Any]) -> tuple[str, int, str | None, list[float], list[dict[str, Any]]]:
        raw_bounds = info.get("total_bounds")
        bounds = [float(value) for value in raw_bounds] if raw_bounds is not None else []
        names = list(info.get("fields") or [])
        dtypes = list(info.get("dtypes") or [])
        fields = [
            {"name": str(name), "type": str(dtypes[index]) if index < len(dtypes) else "object"}
            for index, name in enumerate(names)
        ]
        return (
            str(info.get("geometry_type") or "Unknown"),
            max(0, int(info.get("features") or 0)),
            str(info["crs"]) if info.get("crs") else None,
            bounds,
            fields,
        )

    @staticmethod
    def _dataset_id(source_id: str, format_name: str, path: str, layer_name: str) -> str:
        value = f"{source_id}|{format_name}|{path.lower()}|{layer_name.lower()}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _fingerprint(root: Path, files: list[Path]) -> str:
        digest = hashlib.sha256()
        for path in sorted(files, key=lambda item: item.as_posix().lower()):
            try:
                stat = path.stat()
            except OSError:
                continue
            digest.update(path.relative_to(root).as_posix().lower().encode("utf-8"))
            digest.update(str(stat.st_size).encode("ascii"))
            digest.update(str(stat.st_mtime_ns).encode("ascii"))
        return digest.hexdigest()
