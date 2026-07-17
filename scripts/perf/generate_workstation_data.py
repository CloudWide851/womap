from __future__ import annotations

import argparse
import math
import shutil
from pathlib import Path

if __package__ in {None, ""}:
    from _bootstrap import ensure_repo_root

    ensure_repo_root()

from app.shared.gdal import configure_bundled_gdal

configure_bundled_gdal()

import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402
from rasterio.windows import Window  # noqa: E402

from scripts.perf.generate_ci_data import generate_vector_geojson, sha256_file  # noqa: E402
from scripts.perf.reporting import build_report, write_report  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
PERF_ROOT = (REPO_ROOT / ".womap-data" / "perf").resolve()


def require_managed_output(path: Path) -> Path:
    resolved = path.resolve()
    if resolved != PERF_ROOT and PERF_ROOT not in resolved.parents:
        raise ValueError("workstation data must stay below .womap-data/perf")
    return resolved


def generate_large_raster(path: Path, target_gib: int) -> tuple[int, int]:
    target_bytes = target_gib * 1024**3
    dimension = math.ceil(math.sqrt(target_bytes / 4))
    dimension = math.ceil(dimension / 512) * 512
    block = np.empty((512, 512), dtype=np.float32)
    row_axis = np.arange(512, dtype=np.float32)[:, None]
    column_axis = np.arange(512, dtype=np.float32)[None, :]
    temporary = path.with_suffix(path.suffix + ".tmp")
    with rasterio.open(
        temporary,
        "w",
        driver="GTiff",
        width=dimension,
        height=dimension,
        count=1,
        dtype="float32",
        crs="EPSG:3857",
        transform=from_origin(0, dimension * 10, 10, 10),
        tiled=True,
        blockxsize=512,
        blockysize=512,
        compress="none",
        BIGTIFF="YES",
        nodata=-9999.0,
    ) as dataset:
        for row in range(0, dimension, 512):
            for column in range(0, dimension, 512):
                np.add(row_axis + row, column_axis + column, out=block)
                np.remainder(block, 10000, out=block)
                dataset.write(block, 1, window=Window(column, row, 512, 512))
    temporary.replace(path)
    return dimension, dimension


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the explicit workstation-medium source dataset under ignored storage."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PERF_ROOT / "workstation-medium",
    )
    parser.add_argument("--feature-count", type=int, default=1_000_000)
    parser.add_argument("--raster-gib", type=int, choices=range(10, 21), default=10)
    parser.add_argument("--confirm-large", action="store_true")
    arguments = parser.parse_args()
    if not arguments.confirm_large:
        parser.error("--confirm-large is required because this writes at least 10 GiB")
    if not 1_000_000 <= arguments.feature_count <= 10_000_000:
        parser.error("workstation feature count must be between 1,000,000 and 10,000,000")
    try:
        output = require_managed_output(arguments.output)
    except ValueError as exc:
        parser.error(str(exc))
    output.mkdir(parents=True, exist_ok=True)
    required_bytes = int(arguments.raster_gib * 1024**3 * 1.2)
    if shutil.disk_usage(output).free < required_bytes:
        parser.error("insufficient free space for raster plus staging reserve")

    vector_path = output / "vectors.geojson"
    raster_path = output / "raster-source.tif"
    generate_vector_geojson(vector_path, arguments.feature_count)
    width, height = generate_large_raster(raster_path, arguments.raster_gib)
    report = build_report(
        kind="dataset-manifest",
        profile="workstation-medium",
        dataset_tier="workstation-medium",
        workload={
            "seed_contract": "womap-ci-grid-v1",
            "feature_count": arguments.feature_count,
            "analysis_candidate_count": arguments.feature_count,
            "raster_target_gib": arguments.raster_gib,
            "raster_width": width,
            "raster_height": height,
            "crs": "EPSG:3857",
            "next_step": "import raster-source.tif through WOMAP to create the managed COG",
        },
        metrics={
            "files": [
                {"name": vector_path.name, "bytes": vector_path.stat().st_size, "sha256": sha256_file(vector_path)},
                {"name": raster_path.name, "bytes": raster_path.stat().st_size, "sha256": sha256_file(raster_path)},
            ]
        },
    )
    write_report(output / "manifest.json", report)
    print("Workstation-medium source data generated below .womap-data/perf/workstation-medium.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
