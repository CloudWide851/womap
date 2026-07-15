from __future__ import annotations

import hashlib
import math
import os
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Any

from app.features.imports.schemas import (
    CatalogDataset,
    ImportCatalog,
    RasterBandMetadata,
    RasterMetadata,
)
from app.shared.gdal import configure_bundled_gdal


configure_bundled_gdal()

SHP_REQUIRED = (".shp", ".shx", ".dbf")
SHP_OPTIONAL = (".prj", ".cpg", ".sbn", ".sbx", ".xml")
RASTER_FORMATS = {
    ".tif": "tif",
    ".tiff": "tif",
    ".img": "img",
    ".jp2": "jp2",
    ".j2k": "jp2",
    ".vrt": "vrt",
    ".hdf": "hdf",
    ".h4": "hdf",
    ".h5": "hdf",
    ".he5": "hdf",
    ".nc": "netcdf",
    ".nc4": "netcdf",
    ".cdf": "netcdf",
}
REMOTE_VRT_PREFIXES = ("http://", "https://", "ftp://", "/vsi")


class DatasetScanner:
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
                path = current_path / file_name
                suffix = path.suffix.lower()
                if suffix == ".shp":
                    datasets.append(self._scan_shapefile(source_id, resolved_root, path))
                elif suffix in RASTER_FORMATS:
                    datasets.extend(self._scan_raster(source_id, resolved_root, path))

        for gdb_path in sorted(gdb_paths):
            datasets.extend(self._scan_gdb(source_id, resolved_root, gdb_path))

        return ImportCatalog(
            source_id=source_id,
            scanned_at=datetime.now(UTC).isoformat(),
            datasets=sorted(
                datasets,
                key=lambda item: (
                    item.dataset_kind,
                    item.container.lower(),
                    item.layer_name.lower(),
                ),
            ),
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
        relevant_files = [
            sibling_map[suffix] for suffix in sibling_map if suffix in SHP_REQUIRED + SHP_OPTIONAL
        ]
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
                errors.append(f"无法读取 Shapefile：{self._safe_error(exc, root)}")

        return CatalogDataset(
            id=dataset_id,
            source_id=source_id,
            format="shp",
            dataset_kind="vector",
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
                    dataset_kind="vector",
                    container=relative_path,
                    relative_path=relative_path,
                    layer_name=gdb_path.stem,
                    fingerprint=fingerprint,
                    valid=False,
                    errors=[f"无法读取 FileGDB：{self._safe_error(exc, root)}"],
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
                errors.append(f"无法读取 GDB 图层：{self._safe_error(exc, root)}")
            datasets.append(
                CatalogDataset(
                    id=self._dataset_id(source_id, "gdb", relative_path, str(layer_name)),
                    source_id=source_id,
                    format="gdb",
                    dataset_kind="vector",
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

    def _scan_raster(self, source_id: str, root: Path, path: Path) -> list[CatalogDataset]:
        format_name = RASTER_FORMATS[path.suffix.lower()]
        relative_path = path.relative_to(root).as_posix()
        referenced_files = [path]
        try:
            if format_name == "vrt":
                referenced_files.extend(self._validate_vrt(path, root))
            import rasterio

            with rasterio.open(path) as dataset:
                subdatasets = list(dataset.subdatasets)
                if subdatasets:
                    entries = [
                        self._raster_entry(
                            source_id,
                            root,
                            path,
                            format_name,
                            uri,
                            self._subdataset_label(uri, index),
                            referenced_files,
                        )
                        for index, uri in enumerate(subdatasets, start=1)
                    ]
                    valid_entries = [entry for entry in entries if entry.valid]
                    return valid_entries or entries
                return [
                    self._raster_entry(
                        source_id,
                        root,
                        path,
                        format_name,
                        str(path),
                        path.stem,
                        referenced_files,
                    )
                ]
        except Exception as exc:
            return [
                CatalogDataset(
                    id=self._dataset_id(source_id, format_name, relative_path, path.stem),
                    source_id=source_id,
                    format=format_name,
                    dataset_kind="raster",
                    container=path.parent.relative_to(root).as_posix() or ".",
                    relative_path=relative_path,
                    layer_name=path.stem,
                    geometry_type="Raster",
                    fingerprint=self._fingerprint(root, referenced_files),
                    valid=False,
                    errors=[f"无法读取栅格：{self._safe_error(exc, root)}"],
                )
            ]

    def _raster_entry(
        self,
        source_id: str,
        root: Path,
        path: Path,
        format_name: str,
        uri: str,
        label: str,
        fingerprint_files: list[Path],
    ) -> CatalogDataset:
        import rasterio

        relative_path = path.relative_to(root).as_posix()
        errors: list[str] = []
        try:
            with rasterio.open(uri) as dataset:
                crs = dataset.crs.to_string() if dataset.crs else None
                bounds = [float(value) for value in dataset.bounds]
                nodata = [self._finite_or_none(value) for value in dataset.nodatavals]
                color_interpretation = [item.name for item in dataset.colorinterp]
                bands = [
                    RasterBandMetadata(
                        index=index,
                        name=(dataset.descriptions[index - 1] or f"Band {index}"),
                        dtype=str(dataset.dtypes[index - 1]),
                        nodata=nodata[index - 1],
                        color_interpretation=(
                            color_interpretation[index - 1]
                            if index - 1 < len(color_interpretation)
                            else "undefined"
                        ),
                    )
                    for index in range(1, dataset.count + 1)
                ]
                if dataset.width <= 0 or dataset.height <= 0 or dataset.count <= 0:
                    errors.append("栅格没有可读取的像元或波段。")
                if not crs:
                    errors.append("栅格缺少 CRS；导入时需要指定 EPSG 覆盖值。")
                raster = RasterMetadata(
                    width=dataset.width,
                    height=dataset.height,
                    band_count=dataset.count,
                    driver=dataset.driver,
                    dtypes=[str(value) for value in dataset.dtypes],
                    nodata=nodata,
                    resolution=[abs(float(dataset.res[0])), abs(float(dataset.res[1]))],
                    byte_size=path.stat().st_size,
                    subdataset=label if uri != str(path) else None,
                    bands=bands,
                    source_uri=uri,
                )
        except Exception as exc:
            raster = None
            crs = None
            bounds = []
            errors.append(f"无法读取栅格变量：{self._safe_error(exc, root)}")

        return CatalogDataset(
            id=self._dataset_id(source_id, format_name, relative_path, label),
            source_id=source_id,
            format=format_name,
            dataset_kind="raster",
            container=path.parent.relative_to(root).as_posix() or ".",
            relative_path=relative_path,
            layer_name=label,
            geometry_type="Raster",
            crs=crs,
            bounds=bounds,
            raster=raster,
            fingerprint=self._fingerprint(root, fingerprint_files),
            valid=raster is not None and not [error for error in errors if "缺少 CRS" not in error],
            errors=errors,
        )

    @staticmethod
    def _validate_vrt(path: Path, root: Path) -> list[Path]:
        try:
            tree = ET.parse(path)
        except (OSError, ET.ParseError) as exc:
            raise ValueError("VRT XML 无效。") from exc
        referenced: list[Path] = []
        for node in tree.findall(".//SourceFilename"):
            value = (node.text or "").strip()
            lowered = value.lower().replace("\\", "/")
            windows_path = PureWindowsPath(value)
            if (
                not value
                or node.attrib.get("relativeToVRT") != "1"
                or lowered.startswith(REMOTE_VRT_PREFIXES)
                or Path(value).is_absolute()
                or windows_path.is_absolute()
                or ".." in Path(value.replace("\\", "/")).parts
            ):
                raise ValueError("VRT 只允许数据源目录内的相对本地引用。")
            resolved = (path.parent / Path(value.replace("\\", "/"))).resolve()
            if resolved != root and root not in resolved.parents:
                raise ValueError("VRT 引用超出数据源根目录。")
            if not resolved.is_file():
                raise ValueError("VRT 引用的本地文件不存在。")
            referenced.append(resolved)
        return referenced

    @staticmethod
    def _subdataset_label(uri: str, index: int) -> str:
        candidate = uri.rsplit(":", 1)[-1].strip('"').strip()
        candidate = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", candidate).strip("_")
        return candidate[:120] or f"subdataset_{index}"

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
        for path in sorted(set(files), key=lambda item: item.as_posix().lower()):
            try:
                stat = path.stat()
                relative = path.resolve().relative_to(root.resolve()).as_posix()
            except (OSError, ValueError):
                continue
            digest.update(relative.lower().encode("utf-8"))
            digest.update(str(stat.st_size).encode("ascii"))
            digest.update(str(stat.st_mtime_ns).encode("ascii"))
        return digest.hexdigest()

    @staticmethod
    def _finite_or_none(value: float | int | None) -> float | int | None:
        if value is None:
            return None
        try:
            return value if math.isfinite(float(value)) else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_error(exc: Exception, root: Path) -> str:
        message = str(exc).replace(str(root), "<数据源>")
        message = message.replace(str(root).replace("\\", "/"), "<数据源>")
        return message[:500]


# Compatibility for existing imports/tests while the scanner now handles both kinds.
VectorDatasetScanner = DatasetScanner
