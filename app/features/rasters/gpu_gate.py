from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Callable, Literal

from app.features.rasters.formula_backends import (
    FORMULA_GPU_CONTRACT_VERSION,
    GpuBackendError,
    GpuRuntimeInfo,
    probe_cupy_runtime,
)
from app.shared.config import ROOT_DIR, ResolvedPerformanceSettings


GpuGateStatus = Literal["disabled", "unavailable", "missing", "rejected", "passed", "fallback"]
GPU_GATE_ROOT = (ROOT_DIR / ".womap-data" / "perf" / "gpu-gates").resolve()


@dataclass(frozen=True)
class GpuExecutionDecision:
    requested_backend: Literal["cpu", "auto", "cupy"]
    effective_backend: Literal["cpu", "cupy"]
    gate_status: GpuGateStatus
    reason: str
    benchmark_speedup: float | None = None
    runtime_info: GpuRuntimeInfo | None = None

    @property
    def execution_enabled(self) -> bool:
        return self.effective_backend == "cupy"


_CIRCUIT_LOCK = Lock()
_GPU_CIRCUIT_REASON: str | None = None


def open_gpu_circuit(reason: str) -> None:
    global _GPU_CIRCUIT_REASON
    with _CIRCUIT_LOCK:
        _GPU_CIRCUIT_REASON = reason


def gpu_circuit_reason() -> str | None:
    with _CIRCUIT_LOCK:
        return _GPU_CIRCUIT_REASON


def reset_gpu_circuit_for_tests() -> None:
    global _GPU_CIRCUIT_REASON
    with _CIRCUIT_LOCK:
        _GPU_CIRCUIT_REASON = None


def gpu_gate_path(runtime_info: GpuRuntimeInfo, gate_root: Path = GPU_GATE_ROOT) -> Path:
    root = gate_root.resolve()
    return root / f"{runtime_info.fingerprint}.json"


def resolve_gpu_execution(
    performance: ResolvedPerformanceSettings,
    *,
    gate_root: Path = GPU_GATE_ROOT,
    runtime_probe: Callable[[int], GpuRuntimeInfo] = probe_cupy_runtime,
) -> GpuExecutionDecision:
    requested = performance.gpu_requested_backend
    if requested == "cpu":
        return GpuExecutionDecision(
            requested_backend=requested,
            effective_backend="cpu",
            gate_status="disabled",
            reason="cpu_backend_is_default",
        )

    circuit_reason = gpu_circuit_reason()
    if circuit_reason is not None:
        return GpuExecutionDecision(
            requested_backend=requested,
            effective_backend="cpu",
            gate_status="fallback",
            reason="gpu_circuit_open",
        )

    try:
        runtime_info = runtime_probe(performance.gpu_device_index)
    except GpuBackendError as exc:
        return GpuExecutionDecision(
            requested_backend=requested,
            effective_backend="cpu",
            gate_status="unavailable",
            reason=exc.reason,
        )
    except Exception:
        return GpuExecutionDecision(
            requested_backend=requested,
            effective_backend="cpu",
            gate_status="unavailable",
            reason="gpu_runtime_error",
        )

    path = gpu_gate_path(runtime_info, gate_root)
    if not path.is_file():
        return GpuExecutionDecision(
            requested_backend=requested,
            effective_backend="cpu",
            gate_status="missing",
            reason="local_gpu_benchmark_missing",
            runtime_info=runtime_info,
        )

    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        workload = report["workload"]
        metrics = report["metrics"]
        correctness = metrics["correctness"]
        gate = metrics["gate"]
        speedup = float(gate["speedup"])
        if not math.isfinite(speedup) or speedup < 0:
            raise ValueError("invalid GPU speedup")
        valid = (
            report.get("schema_version") == "womap.performance-report/v1"
            and report.get("kind") == "gpu-formula"
            and workload.get("contract_version") == FORMULA_GPU_CONTRACT_VERSION
            and workload.get("dataset_tier") == "workstation-medium"
            and metrics.get("gpu_fingerprint") == runtime_info.fingerprint
            and correctness.get("passed") is True
            and correctness.get("nodata_mask_equal") is True
            and correctness.get("all_ast_operations") is True
            and gate.get("eligible") is True
            and gate.get("passed") is True
            and gate.get("per_formula_non_regression") is True
            and speedup >= performance.gpu_minimum_speedup
        )
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
        return GpuExecutionDecision(
            requested_backend=requested,
            effective_backend="cpu",
            gate_status="rejected",
            reason="local_gpu_benchmark_invalid",
            runtime_info=runtime_info,
        )

    if not valid:
        return GpuExecutionDecision(
            requested_backend=requested,
            effective_backend="cpu",
            gate_status="rejected",
            reason="local_gpu_benchmark_rejected",
            benchmark_speedup=speedup,
            runtime_info=runtime_info,
        )
    return GpuExecutionDecision(
        requested_backend=requested,
        effective_backend="cupy",
        gate_status="passed",
        reason="local_gpu_benchmark_passed",
        benchmark_speedup=speedup,
        runtime_info=runtime_info,
    )
