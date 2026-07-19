from __future__ import annotations

import argparse
import os
import shutil
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

if __package__ in {None, ""}:
    from _bootstrap import ensure_repo_root

    ensure_repo_root()

import numpy as np

from app.features.rasters.formula_backends import (
    FORMULA_GPU_CONTRACT_VERSION,
    CupyFormulaBackend,
    GpuRuntimeInfo,
    NumpyFormulaBackend,
    probe_cupy_runtime,
)
from app.features.rasters.gpu_gate import GpuExecutionDecision, gpu_gate_path
from app.features.rasters.processor import RasterProcessor
from app.features.rasters.schemas import FormulaNode
from app.features.rasters.storage import RasterStorage
from app.shared.config import ROOT_DIR
from app.shared.runtime_performance import resolve_runtime_performance
from scripts.perf.reporting import build_report, write_report


PERF_ROOT = (ROOT_DIR / ".womap-data" / "perf").resolve()
RUN_ROOT = (PERF_ROOT / "runs").resolve()
DEFAULT_CI_SOURCE = PERF_ROOT / "ci-small" / "raster.tif"
DEFAULT_WORKSTATION_SOURCE = (
    PERF_ROOT / "datasets" / "workstation-medium" / "raster-source.tif"
)


def require_perf_path(path: Path) -> Path:
    resolved = path.resolve()
    if resolved == PERF_ROOT or PERF_ROOT not in resolved.parents:
        raise ValueError("GPU benchmark paths must stay below .womap-data/perf")
    return resolved


def band(index: int = 1) -> FormulaNode:
    return FormulaNode(kind="band", band=index)


def number(value: float) -> FormulaNode:
    return FormulaNode(kind="number", value=value)


def binary(operator: str, left: FormulaNode, right: FormulaNode) -> FormulaNode:
    return FormulaNode(kind="binary", operator=operator, left=left, right=right)


def function(name: str, *arguments: FormulaNode) -> FormulaNode:
    return FormulaNode(kind="function", name=name, arguments=list(arguments))


def benchmark_formulas() -> dict[str, FormulaNode]:
    return {
        "simple": binary("*", band(), number(1.1)),
        "complex": function(
            "clamp",
            binary(
                "*",
                function(
                    "log",
                    function("sqrt", binary("+", function("abs", band()), number(1.0))),
                ),
                number(2.5),
            ),
            number(0.0),
            number(50.0),
        ),
    }


def correctness_formulas() -> list[FormulaNode]:
    first = band(1)
    second = band(2)
    return [
        FormulaNode(kind="unary", operator="+", argument=first),
        FormulaNode(kind="unary", operator="-", argument=first),
        *[binary(operator, first, second) for operator in ("+", "-", "*", "/", "^")],
        function("abs", FormulaNode(kind="unary", operator="-", argument=first)),
        function("sqrt", first),
        function("log", first),
        function("min", first, second),
        function("max", first, second),
        function("clamp", first, number(1.5), number(3.5)),
        number(7.25),
    ]


def verify_correctness(runtime: GpuRuntimeInfo, memory_fraction: float) -> dict[str, object]:
    data = np.asarray(
        [
            [
                [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
                [[2.0, 1.5, 2.5], [2.0, 2.5, 3.0]],
            ],
            [
                [[0.5, 1.5, 2.5], [3.5, 4.5, 5.5]],
                [[1.5, 2.0, 2.5], [3.0, 3.5, 4.0]],
            ],
        ],
        dtype=np.float32,
    )
    masks = np.zeros(data.shape, dtype=np.bool_)
    masks[0, 0, 0, 1] = True
    masks[1, 1, 1, 2] = True
    cpu = NumpyFormulaBackend()
    gpu = CupyFormulaBackend(
        device_index=runtime.device_index,
        memory_fraction=memory_fraction,
    )
    formulas = correctness_formulas()
    try:
        for formula in formulas:
            expected = cpu.evaluate_batch(formula, data, masks, [1, 2])
            actual = gpu.evaluate_batch(formula, data, masks, [1, 2])
            if not np.array_equal(expected.invalid_mask, actual.invalid_mask):
                return {
                    "passed": False,
                    "nodata_mask_equal": False,
                    "all_ast_operations": False,
                    "formula_count": len(formulas),
                    "rtol": 1e-5,
                    "atol": 1e-6,
                }
            valid = ~expected.invalid_mask
            np.testing.assert_allclose(
                actual.output[valid],
                expected.output[valid],
                rtol=1e-5,
                atol=1e-6,
            )
    except (AssertionError, ValueError):
        return {
            "passed": False,
            "nodata_mask_equal": True,
            "all_ast_operations": False,
            "formula_count": len(formulas),
            "rtol": 1e-5,
            "atol": 1e-6,
        }
    finally:
        gpu.release()
    return {
        "passed": True,
        "nodata_mask_equal": True,
        "all_ast_operations": True,
        "formula_count": len(formulas),
        "rtol": 1e-5,
        "atol": 1e-6,
    }


@dataclass(frozen=True)
class FormulaSample:
    backend: str
    formula: str
    round_index: int
    cold: bool
    duration_seconds: float
    phase_timings_ms: dict[str, object]
    max_batch_windows: int


def _link_or_copy(source: Path, destination: Path) -> None:
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def run_formula_sample(
    *,
    source: Path,
    run_root: Path,
    formula_name: str,
    formula: FormulaNode,
    backend_name: str,
    round_index: int,
    cold: bool,
    runtime: GpuRuntimeInfo,
    quota_gib: int,
) -> FormulaSample:
    sample_root = require_perf_path(
        run_root / f"{formula_name}-{round_index}-{backend_name}-{uuid4().hex[:8]}"
    )
    performance = resolve_runtime_performance()
    storage = RasterStorage(
        str(sample_root / "store"),
        str(sample_root / "scratch"),
        quota_gib,
    )
    managed_source = storage.root / "source.tif"
    _link_or_copy(source, managed_source)
    if backend_name == "cupy":
        backend = CupyFormulaBackend(
            device_index=runtime.device_index,
            memory_fraction=performance.gpu_memory_fraction,
        )
        decision = GpuExecutionDecision(
            requested_backend="cupy",
            effective_backend="cupy",
            gate_status="passed",
            reason="benchmark_direct_execution",
            runtime_info=runtime,
        )
    else:
        backend = NumpyFormulaBackend()
        decision = GpuExecutionDecision(
            requested_backend="cpu",
            effective_backend="cpu",
            gate_status="disabled",
            reason="benchmark_cpu_baseline",
        )
    try:
        processor = RasterProcessor(
            storage,
            performance,
            gpu_decision=decision,
            formula_backend=backend,
        )
        started = time.perf_counter()
        result = processor.materialize_formula(
            managed_source,
            f"gpu-benchmark-{formula_name}-{round_index}",
            uuid4().hex,
            formula,
        )
        duration = time.perf_counter() - started
        execution = result.formula_execution
        if execution is None or execution.effective_backend != backend_name:
            raise RuntimeError("GPU benchmark did not execute the requested backend")
        return FormulaSample(
            backend=backend_name,
            formula=formula_name,
            round_index=round_index,
            cold=cold,
            duration_seconds=duration,
            phase_timings_ms=result.phase_timings.public_summary(),
            max_batch_windows=execution.max_batch_windows,
        )
    finally:
        backend.release()
        resolved = sample_root.resolve()
        if resolved.parent == run_root.resolve() and resolved.is_dir():
            shutil.rmtree(resolved)


def run_benchmark(
    *,
    source: Path,
    dataset_tier: str,
    runtime: GpuRuntimeInfo,
    warm_samples: int,
    quota_gib: int,
) -> list[FormulaSample]:
    source = require_perf_path(source)
    if not source.is_file():
        raise FileNotFoundError(source.name)
    run_root = require_perf_path(RUN_ROOT / f"gpu-formula-{uuid4().hex}")
    run_root.mkdir(parents=True, exist_ok=False)
    samples: list[FormulaSample] = []
    try:
        for formula_index, (formula_name, formula) in enumerate(benchmark_formulas().items()):
            for round_index in range(warm_samples + 1):
                cold = round_index == 0
                order = ["cpu", "cupy"]
                if (round_index + formula_index) % 2:
                    order.reverse()
                for backend_name in order:
                    sample = run_formula_sample(
                        source=source,
                        run_root=run_root,
                        formula_name=formula_name,
                        formula=formula,
                        backend_name=backend_name,
                        round_index=round_index,
                        cold=cold,
                        runtime=runtime,
                        quota_gib=quota_gib,
                    )
                    samples.append(sample)
                    print(
                        f"completed {formula_name} round={round_index} "
                        f"backend={backend_name} seconds={sample.duration_seconds:.3f}",
                        flush=True,
                    )
        return samples
    finally:
        if run_root.parent == RUN_ROOT and run_root.is_dir():
            shutil.rmtree(run_root)


def summarize_samples(samples: list[FormulaSample], initialization_ms: int) -> dict[str, object]:
    formula_metrics: dict[str, object] = {}
    all_cpu: list[float] = []
    all_gpu: list[float] = []
    for formula_name in benchmark_formulas():
        selected = [sample for sample in samples if sample.formula == formula_name]
        cpu_warm = [
            sample.duration_seconds
            for sample in selected
            if sample.backend == "cpu" and not sample.cold
        ]
        gpu_warm = [
            sample.duration_seconds
            for sample in selected
            if sample.backend == "cupy" and not sample.cold
        ]
        cpu_cold = next(
            sample.duration_seconds
            for sample in selected
            if sample.backend == "cpu" and sample.cold
        )
        gpu_cold = next(
            sample.duration_seconds
            for sample in selected
            if sample.backend == "cupy" and sample.cold
        ) + initialization_ms / 1000
        cpu_median = statistics.median(cpu_warm)
        gpu_median = statistics.median(gpu_warm)
        all_cpu.extend(cpu_warm)
        all_gpu.extend(gpu_warm)
        last_gpu = next(sample for sample in reversed(selected) if sample.backend == "cupy")
        formula_metrics[formula_name] = {
            "cold_cpu_seconds": round(cpu_cold, 6),
            "cold_gpu_seconds_including_initialization": round(gpu_cold, 6),
            "warm_cpu_seconds": [round(value, 6) for value in cpu_warm],
            "warm_gpu_seconds": [round(value, 6) for value in gpu_warm],
            "warm_cpu_median_seconds": round(cpu_median, 6),
            "warm_gpu_median_seconds": round(gpu_median, 6),
            "speedup": round(cpu_median / max(gpu_median, 1e-9), 6),
            "gpu_phase_timings_ms": last_gpu.phase_timings_ms,
            "gpu_max_batch_windows": last_gpu.max_batch_windows,
        }
    return {
        "formulas": formula_metrics,
        "aggregate_speedup": round(sum(all_cpu) / max(sum(all_gpu), 1e-9), 6),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark end-to-end NumPy/CuPy raster formula execution."
    )
    parser.add_argument(
        "--profile",
        choices=("ci-small", "workstation-medium"),
        default="ci-small",
    )
    parser.add_argument("--source", type=Path)
    parser.add_argument("--warm-samples", type=int, default=3)
    parser.add_argument("--quota-gib", type=int, default=200)
    parser.add_argument("--confirm-large", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=PERF_ROOT / "reports" / "gpu-formula-ci-small.json",
    )
    arguments = parser.parse_args()
    if not 1 <= arguments.warm_samples <= 5:
        parser.error("warm samples must be between 1 and 5")
    if arguments.profile == "workstation-medium" and not arguments.confirm_large:
        parser.error("workstation-medium requires --confirm-large")
    source = arguments.source or (
        DEFAULT_WORKSTATION_SOURCE
        if arguments.profile == "workstation-medium"
        else DEFAULT_CI_SOURCE
    )
    source = require_perf_path(source)
    runtime = probe_cupy_runtime(resolve_runtime_performance().gpu_device_index)
    correctness = verify_correctness(
        runtime,
        resolve_runtime_performance().gpu_memory_fraction,
    )
    samples = run_benchmark(
        source=source,
        dataset_tier=arguments.profile,
        runtime=runtime,
        warm_samples=arguments.warm_samples,
        quota_gib=arguments.quota_gib,
    )
    summary = summarize_samples(samples, runtime.initialization_ms)
    minimum_speedup = resolve_runtime_performance().gpu_minimum_speedup
    formula_metrics = summary["formulas"]
    per_formula_non_regression = all(
        float(value["speedup"]) >= 1.0 for value in formula_metrics.values()
    )
    aggregate_speedup = float(summary["aggregate_speedup"])
    eligible = arguments.profile == "workstation-medium"
    passed = (
        eligible
        and correctness["passed"] is True
        and per_formula_non_regression
        and aggregate_speedup >= minimum_speedup
    )
    report = build_report(
        kind="gpu-formula",
        profile=arguments.profile,
        dataset_tier=arguments.profile,
        workload={
            "contract_version": FORMULA_GPU_CONTRACT_VERSION,
            "dataset_tier": arguments.profile,
            "cold_samples": 1,
            "warm_samples": arguments.warm_samples,
            "execution_order": "alternating-cpu-cupy",
            "minimum_speedup": minimum_speedup,
        },
        metrics={
            "gpu_fingerprint": runtime.fingerprint,
            "correctness": correctness,
            "timings": summary,
            "gate": {
                "eligible": eligible,
                "passed": passed,
                "speedup": aggregate_speedup,
                "per_formula_non_regression": per_formula_non_regression,
            },
        },
    )
    output = (
        gpu_gate_path(runtime)
        if arguments.profile == "workstation-medium"
        else require_perf_path(arguments.output)
    )
    write_report(output, report)
    status = "passed" if passed else "rejected"
    print(
        f"GPU formula benchmark {status}; speedup={aggregate_speedup:.3f}x; "
        f"eligible={str(eligible).lower()}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
