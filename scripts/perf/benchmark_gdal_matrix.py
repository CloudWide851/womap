from __future__ import annotations

import argparse
import shutil
import statistics
import time
from pathlib import Path
from uuid import uuid4

if __package__ in {None, ""}:
    from _bootstrap import ensure_repo_root

    ensure_repo_root()

from app.features.rasters.processor import RasterProcessor
from app.features.rasters.schemas import FormulaNode
from app.features.rasters.storage import RasterStorage
from app.shared.config import ROOT_DIR
from app.shared.runtime_performance import resolve_runtime_performance
from scripts.perf.reporting import build_report, write_report


PERF_ROOT = (ROOT_DIR / ".womap-data" / "perf").resolve()


def require_perf_path(path: Path) -> Path:
    resolved = path.resolve()
    if resolved == PERF_ROOT or PERF_ROOT not in resolved.parents:
        raise ValueError("GDAL matrix paths must stay below .womap-data/perf")
    return resolved


def parse_values(value: str) -> list[int]:
    try:
        values = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("values must be comma-separated integers") from exc
    if not values or len(values) > 8 or any(item <= 0 for item in values):
        raise argparse.ArgumentTypeError("values must contain 1..8 positive integers")
    return values


def matrix_profile(dimension: str, value: int):
    maximum = {"threads": 32, "cache": 4096, "window": 2048}[dimension]
    if value > maximum:
        raise ValueError(f"{dimension} value exceeds the bounded maximum {maximum}")
    baseline = resolve_runtime_performance()
    field = {
        "threads": "gdal_threads",
        "cache": "gdal_cache_mib",
        "window": "formula_window_budget_mib",
    }[dimension]
    return baseline.model_copy(update={field: value})


def run_matrix(
    *,
    source: Path,
    operation: str,
    dimension: str,
    values: list[int],
    quota_gib: int,
    warmups: int = 1,
    samples: int = 3,
) -> list[dict[str, object]]:
    source = require_perf_path(source)
    if not source.is_file():
        raise FileNotFoundError(source.name)
    run_id = uuid4().hex
    run_root = require_perf_path(PERF_ROOT / "runs" / f"gdal-matrix-{run_id}")
    results: list[dict[str, object]] = []
    try:
        for value in values:
            durations: list[float] = []
            result = None
            for iteration in range(warmups + samples):
                variant = run_root / f"{dimension}-{value}-{iteration}"
                storage = RasterStorage(
                    str(variant / "store"), str(variant / "scratch"), quota_gib
                )
                processor = RasterProcessor(storage, matrix_profile(dimension, value))
                started = time.perf_counter()
                if operation == "convert":
                    result = processor.to_cog(
                        str(source),
                        dataset_id=f"matrix-{value}-{iteration}",
                        fingerprint=uuid4().hex,
                    )
                else:
                    managed_source = storage.root / source.name
                    shutil.copy2(source, managed_source)
                    result = processor.materialize_formula(
                        managed_source,
                        f"formula-{value}-{iteration}",
                        uuid4().hex,
                        FormulaNode(kind="band", band=1),
                    )
                duration = time.perf_counter() - started
                if iteration >= warmups:
                    durations.append(duration)
            if result is None:
                raise RuntimeError("GDAL matrix produced no result")
            duration = statistics.median(durations)
            source_bytes = source.stat().st_size
            results.append(
                {
                    "value": value,
                    "warmups": warmups,
                    "samples": samples,
                    "duration_median_seconds": round(duration, 6),
                    "duration_samples_seconds": [round(item, 6) for item in durations],
                    "throughput_mib_s": round(source_bytes / 1024**2 / max(duration, 1e-9), 3),
                    "phase_timings_ms": result.phase_timings.public_summary(),
                    "space_estimate_bytes": result.space_estimate.public_summary(),
                }
            )
        baseline_throughput = float(results[0]["throughput_mib_s"])
        comparison_available = len(results) > 1
        for result in results:
            throughput = float(result["throughput_mib_s"])
            result["comparison_available"] = comparison_available
            result["speedup_vs_baseline"] = (
                round(throughput / max(baseline_throughput, 1e-9), 3)
                if comparison_available
                else None
            )
            result["meets_complexity_gate"] = (
                throughput >= baseline_throughput * 1.20 if comparison_available else None
            )
        return results
    finally:
        if run_root.is_dir() and run_root.parent == (PERF_ROOT / "runs").resolve():
            shutil.rmtree(run_root)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark one bounded GDAL resource dimension at a time."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--operation", choices=("convert", "formula"), default="convert")
    parser.add_argument("--dimension", choices=("threads", "cache", "window"), required=True)
    parser.add_argument("--values", type=parse_values, required=True)
    parser.add_argument("--quota-gib", type=int, default=200)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--profile", choices=("ci-small", "workstation-medium"), default="ci-small")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".womap-data/perf/reports/gdal-matrix.json"),
    )
    arguments = parser.parse_args()
    if arguments.dimension == "window" and arguments.operation != "formula":
        parser.error("window dimension requires --operation formula")
    if arguments.dimension != "window" and arguments.operation == "formula":
        parser.error("formula operation only varies the window dimension")
    if not 0 <= arguments.warmups <= 5 or not 1 <= arguments.samples <= 10:
        parser.error("warmups must be 0..5 and samples must be 1..10")
    output = require_perf_path(arguments.output)
    results = run_matrix(
        source=arguments.source,
        operation=arguments.operation,
        dimension=arguments.dimension,
        values=arguments.values,
        quota_gib=arguments.quota_gib,
        warmups=arguments.warmups,
        samples=arguments.samples,
    )
    write_report(
        output,
        build_report(
            kind="gdal-matrix",
            profile=arguments.profile,
            dataset_tier=arguments.profile,
            workload={
                "operation": arguments.operation,
                "dimension": arguments.dimension,
                "values": arguments.values,
                "minimum_complexity_speedup": 1.20,
                "warmups": arguments.warmups,
                "samples": arguments.samples,
            },
            metrics={"variants": results},
        ),
    )
    print("GDAL matrix completed; temporary run assets were removed by exact run-id.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
