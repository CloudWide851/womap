from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.features.rasters.formula_backends import GpuBackendUnavailable, GpuRuntimeInfo
from app.features.rasters.gpu_gate import (
    gpu_gate_path,
    open_gpu_circuit,
    reset_gpu_circuit_for_tests,
    resolve_gpu_execution,
)
from app.shared.config import PerformanceSettings


def _profile(backend: str = "auto", minimum_speedup: float = 1.5):
    return PerformanceSettings.model_validate(
        {"gpu": {"backend": backend, "minimum_speedup": minimum_speedup}}
    ).resolve(logical_cpu_count=8, total_memory_bytes=16 * 1024**3)


def _runtime(fingerprint: str = "a" * 64) -> GpuRuntimeInfo:
    return GpuRuntimeInfo(
        fingerprint=fingerprint,
        device_index=0,
        device_name="Example GPU",
        compute_capability="8.6",
        driver_version="58129",
        cuda_runtime_version="12060",
        cupy_version="14.1.0",
        total_memory_bytes=6 * 1024**3,
        initialization_ms=12,
    )


def _report(runtime: GpuRuntimeInfo, *, speedup: float = 1.6, passed: bool = True):
    return {
        "schema_version": "womap.performance-report/v1",
        "kind": "gpu-formula",
        "created_at": "2026-07-19T00:00:00Z",
        "environment": {},
        "workload": {
            "contract_version": "womap.raster-formula-gpu/v1",
            "dataset_tier": "workstation-medium",
        },
        "metrics": {
            "gpu_fingerprint": runtime.fingerprint,
            "correctness": {
                "passed": passed,
                "nodata_mask_equal": passed,
                "all_ast_operations": passed,
            },
            "gate": {
                "eligible": True,
                "passed": passed,
                "speedup": speedup,
                "per_formula_non_regression": passed,
            },
        },
    }


@pytest.fixture(autouse=True)
def _reset_circuit() -> None:
    reset_gpu_circuit_for_tests()
    yield
    reset_gpu_circuit_for_tests()


def test_cpu_is_always_forced_without_probing() -> None:
    called = False

    def probe(_index: int) -> GpuRuntimeInfo:
        nonlocal called
        called = True
        return _runtime()

    decision = resolve_gpu_execution(_profile("cpu"), runtime_probe=probe)

    assert decision.gate_status == "disabled"
    assert decision.effective_backend == "cpu"
    assert called is False


def test_gate_missing_corrupt_mismatch_and_unavailable_fail_closed(tmp_path: Path) -> None:
    runtime = _runtime()
    missing = resolve_gpu_execution(
        _profile(), gate_root=tmp_path, runtime_probe=lambda _index: runtime
    )
    assert missing.gate_status == "missing"

    path = gpu_gate_path(runtime, tmp_path)
    path.write_text("not json", encoding="utf-8")
    corrupt = resolve_gpu_execution(
        _profile(), gate_root=tmp_path, runtime_probe=lambda _index: runtime
    )
    assert corrupt.gate_status == "rejected"
    assert corrupt.reason == "local_gpu_benchmark_invalid"

    path.write_text(json.dumps(_report(_runtime("b" * 64))), encoding="utf-8")
    mismatch = resolve_gpu_execution(
        _profile(), gate_root=tmp_path, runtime_probe=lambda _index: runtime
    )
    assert mismatch.gate_status == "rejected"

    def unavailable(_index: int) -> GpuRuntimeInfo:
        raise GpuBackendUnavailable("cupy_runtime_unavailable")

    unavailable_decision = resolve_gpu_execution(
        _profile(), gate_root=tmp_path, runtime_probe=unavailable
    )
    assert unavailable_decision.gate_status == "unavailable"
    assert unavailable_decision.reason == "cupy_runtime_unavailable"

    runtime_error = resolve_gpu_execution(
        _profile(),
        gate_root=tmp_path,
        runtime_probe=lambda _index: (_ for _ in ()).throw(RuntimeError("driver")),
    )
    assert runtime_error.gate_status == "unavailable"
    assert runtime_error.reason == "gpu_runtime_error"


def test_gate_rejects_correctness_speed_and_per_formula_regressions(tmp_path: Path) -> None:
    runtime = _runtime()
    path = gpu_gate_path(runtime, tmp_path)
    cases = [
        _report(runtime, speedup=1.49),
        _report(runtime, speedup=1.8, passed=False),
    ]
    for report in cases:
        path.write_text(json.dumps(report), encoding="utf-8")
        decision = resolve_gpu_execution(
            _profile(), gate_root=tmp_path, runtime_probe=lambda _index: runtime
        )
        assert decision.gate_status == "rejected"
        assert decision.effective_backend == "cpu"

    report = _report(runtime, speedup=1.8)
    report["metrics"]["gate"]["per_formula_non_regression"] = False
    path.write_text(json.dumps(report), encoding="utf-8")
    decision = resolve_gpu_execution(
        _profile(), gate_root=tmp_path, runtime_probe=lambda _index: runtime
    )
    assert decision.gate_status == "rejected"

    report = _report(runtime)
    report["metrics"]["gate"]["speedup"] = float("nan")
    path.write_text(json.dumps(report), encoding="utf-8")
    invalid_number = resolve_gpu_execution(
        _profile(), gate_root=tmp_path, runtime_probe=lambda _index: runtime
    )
    assert invalid_number.gate_status == "rejected"
    assert invalid_number.benchmark_speedup is None


def test_only_valid_workstation_gate_enables_cupy_and_circuit_reverts_to_cpu(
    tmp_path: Path,
) -> None:
    runtime = _runtime()
    path = gpu_gate_path(runtime, tmp_path)
    path.write_text(json.dumps(_report(runtime, speedup=1.75)), encoding="utf-8")

    passed = resolve_gpu_execution(
        _profile(), gate_root=tmp_path, runtime_probe=lambda _index: runtime
    )
    assert passed.execution_enabled is True
    assert passed.effective_backend == "cupy"
    assert passed.gate_status == "passed"
    assert passed.benchmark_speedup == pytest.approx(1.75)

    open_gpu_circuit("gpu_oom")
    fallback = resolve_gpu_execution(
        _profile(), gate_root=tmp_path, runtime_probe=lambda _index: runtime
    )
    assert fallback.execution_enabled is False
    assert fallback.gate_status == "fallback"
    assert fallback.reason == "gpu_circuit_open"
