from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.features.exports.schemas import ExportFormat, ExportLayer


class ExportWriterError(Exception):
    """Base export writer error."""


class ExportDependencyError(ExportWriterError):
    """Raised when the GDAL-backed writer cannot export the requested format."""


@dataclass(frozen=True)
class ExportArchive:
    path: Path
    cleanup_path: Path
    filename: str
    media_type: str = "application/zip"


def safe_dataset_name(value: str, fallback: str = "layer") -> str:
    normalized = re.sub(r"[^0-9A-Za-z_]+", "_", value).strip("_").lower()
    if not normalized:
        normalized = fallback
    return normalized[:48]


def unique_dataset_name(value: str, used: set[str], fallback: str = "layer") -> str:
    base = safe_dataset_name(value, fallback=fallback)
    candidate = base
    suffix = 1
    while candidate in used:
        suffix += 1
        suffix_text = f"_{suffix}"
        candidate = f"{base[: 48 - len(suffix_text)]}{suffix_text}"
    used.add(candidate)
    return candidate


def build_shapefile_field_mapping(field_names: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    used: set[str] = set()

    for index, original in enumerate(field_names, start=1):
        base = re.sub(r"[^0-9A-Za-z_]+", "_", original).strip("_").upper()
        if not base:
            base = f"FIELD{index}"
        if base[0].isdigit():
            base = f"F_{base}"

        candidate = base[:10].rstrip("_") or base[:10]
        suffix = 1
        while candidate in used:
            suffix += 1
            suffix_text = str(suffix)
            candidate_base = base[: 10 - len(suffix_text)].rstrip("_")
            candidate = f"{candidate_base}{suffix_text}"

        used.add(candidate)
        mapping[original] = candidate

    return mapping


class GdalVectorWriter:
    def write(self, export_format: ExportFormat, layers: list[ExportLayer]) -> ExportArchive:
        root = Path(tempfile.mkdtemp(prefix="womap-export-"))
        payload_root = root / f"womap-export-{export_format}"
        payload_root.mkdir(parents=True, exist_ok=True)

        try:
            if export_format == "shp":
                self._write_shapefile_package(payload_root, layers)
            elif export_format == "gdb":
                self._write_filegdb_package(payload_root, layers)
            else:
                raise ExportDependencyError(f"不支持的导出格式：{export_format}")

            archive_path = Path(
                shutil.make_archive(str(root / f"womap-export-{export_format}"), "zip", payload_root),
            )
            return ExportArchive(
                path=archive_path,
                cleanup_path=root,
                filename=f"womap-export-{export_format}.zip",
            )
        except Exception:
            shutil.rmtree(root, ignore_errors=True)
            raise

    def _write_shapefile_package(self, payload_root: Path, layers: list[ExportLayer]) -> None:
        manifest: dict[str, Any] = {"layers": []}
        used_names: set[str] = set()
        for layer in layers:
            layer_name = unique_dataset_name(layer.name, used_names, fallback=f"layer_{layer.id}")
            layer_dir = payload_root / layer_name
            layer_dir.mkdir(parents=True, exist_ok=True)
            records, field_mapping = self._records_for_layer(layer, shapefile_fields=True)
            dataframe = self._build_dataframe(records, crs=layer.crs)
            shp_path = layer_dir / f"{layer_name}.shp"
            self._write_dataframe(dataframe, shp_path, driver="ESRI Shapefile", encoding="UTF-8")
            manifest["layers"].append(
                {
                    "layer_id": layer.id,
                    "layer_name": layer.name,
                    "dataset": layer_name,
                    "fields": field_mapping,
                },
            )

        (payload_root / "field-map.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _write_filegdb_package(self, payload_root: Path, layers: list[ExportLayer]) -> None:
        gdb_path = payload_root / "womap-export.gdb"
        used_names: set[str] = set()
        for layer in layers:
            layer_name = unique_dataset_name(layer.name, used_names, fallback=f"layer_{layer.id}")
            records, _ = self._records_for_layer(layer, shapefile_fields=False)
            dataframe = self._build_dataframe(records, crs=layer.crs)
            self._write_dataframe(
                dataframe,
                gdb_path,
                driver="OpenFileGDB",
                layer=layer_name,
            )

    def _records_for_layer(
        self,
        layer: ExportLayer,
        *,
        shapefile_fields: bool,
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        fields = sorted({field for feature in layer.features for field in feature.properties})
        field_mapping = build_shapefile_field_mapping(fields) if shapefile_fields else {f: f for f in fields}
        records: list[dict[str, Any]] = []

        for feature in layer.features:
            record: dict[str, Any] = {"womap_id": feature.id}
            for field_name, value in feature.properties.items():
                record[field_mapping.get(field_name, field_name)] = value
            record["geometry"] = feature.geometry
            records.append(record)

        return records, field_mapping

    def _build_dataframe(self, records: list[dict[str, Any]], crs: str | None):
        try:
            import geopandas as gpd
            from shapely.geometry import shape
        except Exception as exc:  # pragma: no cover - exercised through dependency tests
            raise ExportDependencyError("缺少 geopandas/shapely，无法写出 SHP 或 GDB。") from exc

        dataframe_records: list[dict[str, Any]] = []
        geometries = []
        for record in records:
            geometry = record.pop("geometry")
            geometries.append(shape(geometry))
            dataframe_records.append(record)

        return gpd.GeoDataFrame(dataframe_records, geometry=geometries, crs=crs or "EPSG:3857")

    def _write_dataframe(self, dataframe, path: Path, **kwargs: Any) -> None:
        try:
            import pyogrio
        except Exception as exc:  # pragma: no cover - exercised through dependency tests
            raise ExportDependencyError("缺少 pyogrio/GDAL，无法写出 SHP 或 GDB。") from exc

        try:
            pyogrio.write_dataframe(dataframe, path, **kwargs)
        except Exception as exc:
            raise ExportDependencyError(f"GDAL 导出驱动不可用或写入失败：{exc}") from exc
