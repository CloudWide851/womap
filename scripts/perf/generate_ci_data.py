from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    from _bootstrap import ensure_repo_root

    ensure_repo_root()

from app.shared.gdal import configure_bundled_gdal

configure_bundled_gdal()

import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402

from scripts.perf.reporting import build_report, write_report  # noqa: E402


def vector_feature(index: int, columns: int, cell_size: float = 100.0) -> dict[str, Any]:
    row, column = divmod(index, columns)
    left = column * cell_size
    bottom = row * cell_size
    right = left + cell_size * 0.8
    top = bottom + cell_size * 0.8
    return {
        "type": "Feature",
        "id": index + 1,
        "properties": {
            "source_id": f"ci-{index + 1:07d}",
            "group": index % 17,
            "value": round(((index * 2654435761) % 100000) / 100.0, 2),
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [left, bottom],
                    [right, bottom],
                    [right, top],
                    [left, top],
                    [left, bottom],
                ]
            ],
        },
    }


def generate_vector_geojson(path: Path, feature_count: int) -> None:
    columns = max(1, math.ceil(math.sqrt(feature_count)))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write('{"type":"FeatureCollection","name":"womap-ci-small","features":[')
        for index in range(feature_count):
            if index:
                stream.write(",")
            json.dump(vector_feature(index, columns), stream, ensure_ascii=False, separators=(",", ":"))
        stream.write("]}")
    temporary.replace(path)


def generate_raster(path: Path, width: int, height: int) -> None:
    rows = np.arange(height, dtype=np.float32)[:, None]
    columns = np.arange(width, dtype=np.float32)[None, :]
    values = ((rows * 17 + columns * 31) % 10000).astype(np.float32) / 10.0
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with rasterio.open(
        temporary,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="float32",
        crs="EPSG:3857",
        transform=from_origin(0, height * 10, 10, 10),
        tiled=True,
        blockxsize=min(256, width),
        blockysize=min(256, height),
        compress="deflate",
        predictor=3,
        nodata=-9999.0,
    ) as dataset:
        dataset.write(values, 1)
        factors = [factor for factor in (2, 4, 8) if width // factor >= 1 and height // factor >= 1]
        if factors:
            dataset.build_overviews(factors, rasterio.enums.Resampling.average)
            dataset.update_tags(ns="rio_overview", resampling="average")
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def generate_ci_dataset(
    output: Path,
    *,
    feature_count: int = 2500,
    raster_width: int = 512,
    raster_height: int = 512,
) -> dict[str, Any]:
    vector_path = output / "vectors.geojson"
    raster_path = output / "raster.tif"
    generate_vector_geojson(vector_path, feature_count)
    generate_raster(raster_path, raster_width, raster_height)
    manifest = build_report(
        kind="dataset-manifest",
        profile="ci-small",
        dataset_tier="ci-small",
        workload={
            "seed_contract": "womap-ci-grid-v1",
            "feature_count": feature_count,
            "raster_width": raster_width,
            "raster_height": raster_height,
            "crs": "EPSG:3857",
        },
        metrics={
            "files": [
                {
                    "name": vector_path.name,
                    "bytes": vector_path.stat().st_size,
                    "sha256": sha256_file(vector_path),
                },
                {
                    "name": raster_path.name,
                    "bytes": raster_path.stat().st_size,
                    "sha256": sha256_file(raster_path),
                },
            ]
        },
    )
    write_report(output / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic CI-small GIS fixtures.")
    parser.add_argument("--output", type=Path, default=Path(".womap-data/perf/ci-small"))
    parser.add_argument("--feature-count", type=int, default=2500)
    parser.add_argument("--raster-width", type=int, default=512)
    parser.add_argument("--raster-height", type=int, default=512)
    arguments = parser.parse_args()
    if not 1 <= arguments.feature_count <= 100000:
        parser.error("feature count must be between 1 and 100000")
    if not 64 <= arguments.raster_width <= 8192 or not 64 <= arguments.raster_height <= 8192:
        parser.error("raster dimensions must be between 64 and 8192")
    generate_ci_dataset(
        arguments.output,
        feature_count=arguments.feature_count,
        raster_width=arguments.raster_width,
        raster_height=arguments.raster_height,
    )
    print("CI-small data generated: vectors.geojson, raster.tif, manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
