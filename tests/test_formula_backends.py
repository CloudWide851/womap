from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.features.rasters import formula_backends
from app.features.rasters.formula_backends import (
    CupyFormulaBackend,
    FormulaBackendTimings,
    FormulaBatchResult,
    GpuBackendRuntimeError,
    GpuBackendUnavailable,
    NumpyFormulaBackend,
    probe_cupy_runtime,
)
from app.features.rasters.gpu_gate import (
    GpuExecutionDecision,
    gpu_circuit_reason,
    reset_gpu_circuit_for_tests,
)
from app.features.jobs.schemas import RasterJobProgressDetail
from app.features.rasters.processor import RasterProcessor
from app.features.rasters.schemas import FormulaNode
from app.features.rasters.storage import RasterStorage
from app.shared.config import PerformanceSettings


def _band(index: int = 1) -> FormulaNode:
    return FormulaNode(kind="band", band=index)


def _number(value: float) -> FormulaNode:
    return FormulaNode(kind="number", value=value)


def _binary(operator: str, left: FormulaNode, right: FormulaNode) -> FormulaNode:
    return FormulaNode(kind="binary", operator=operator, left=left, right=right)


def _function(name: str, *arguments: FormulaNode) -> FormulaNode:
    return FormulaNode(kind="function", name=name, arguments=list(arguments))


def _profile(backend: str = "cpu"):
    return PerformanceSettings.model_validate(
        {"gpu": {"backend": backend}, "gdal": {"formula_window_budget_mib": 32}}
    ).resolve(logical_cpu_count=8, total_memory_bytes=16 * 1024**3)


@pytest.mark.parametrize(
    "formula, expected",
    [
        (_binary("+", _band(1), _band(2)), 6.0),
        (_binary("-", _band(1), _band(2)), 2.0),
        (_binary("*", _band(1), _band(2)), 8.0),
        (_binary("/", _band(1), _band(2)), 2.0),
        (_binary("^", _band(1), _band(2)), 16.0),
        (FormulaNode(kind="unary", operator="-", argument=_band(1)), -4.0),
        (_function("abs", FormulaNode(kind="unary", operator="-", argument=_band(1))), 4.0),
        (_function("sqrt", _band(1)), 2.0),
        (_function("log", _band(1)), float(np.log(4.0))),
        (_function("min", _band(1), _band(2)), 2.0),
        (_function("max", _band(1), _band(2)), 4.0),
        (_function("clamp", _band(1), _number(1.0), _number(3.0)), 3.0),
    ],
)
def test_numpy_backend_is_authoritative_for_all_ast_nodes(
    formula: FormulaNode,
    expected: float,
) -> None:
    data = np.asarray([[[[4.0]], [[2.0]]]], dtype=np.float32)
    masks = np.zeros(data.shape, dtype=np.bool_)

    result = NumpyFormulaBackend().evaluate_batch(formula, data, masks, [1, 2])

    assert result.output.dtype == np.float32
    assert result.invalid_mask.dtype == np.bool_
    assert result.output[0, 0, 0] == pytest.approx(expected, rel=1e-5, abs=1e-6)


def test_numpy_backend_unions_masks_broadcasts_constants_and_normalizes_non_finite() -> None:
    data = np.asarray([[[[1.0, 2.0]], [[0.0, 4.0]]]], dtype=np.float32)
    masks = np.zeros(data.shape, dtype=np.bool_)
    masks[0, 1, 0, 1] = True
    backend = NumpyFormulaBackend()

    divided = backend.evaluate_batch(_binary("/", _band(1), _band(2)), data, masks, [1, 2])
    constant = backend.evaluate_batch(_number(9.0), data[:, :1], masks[:, :1], [1])

    assert divided.invalid_mask.tolist() == [[[True, True]]]
    assert divided.output.tolist() == [[[-9999.0, -9999.0]]]
    assert constant.output.tolist() == [[[9.0, 9.0]]]


def test_cupy_is_lazy_and_missing_runtime_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_name: str):
        raise ImportError("not installed")

    monkeypatch.setattr(formula_backends.importlib, "import_module", missing)
    backend = CupyFormulaBackend(device_index=0, memory_fraction=0.5)

    with pytest.raises(GpuBackendUnavailable, match="cupy_runtime_unavailable"):
        backend.batch_capacity(
            window_width=512,
            window_height=512,
            band_count=1,
            host_budget_bytes=64 * 1024**2,
        )


def test_gpu_batch_capacity_honors_host_vram_reserve_and_fixed_cap() -> None:
    class Device:
        def __init__(self, _index: int) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    fake = SimpleNamespace(
        cuda=SimpleNamespace(
            Device=Device,
            runtime=SimpleNamespace(
                memGetInfo=lambda: (2 * 1024**3, 6 * 1024**3),
            ),
        )
    )
    backend = CupyFormulaBackend(device_index=0, memory_fraction=0.5, cupy_module=fake)

    capacity = backend.batch_capacity(
        window_width=512,
        window_height=512,
        band_count=1,
        host_budget_bytes=8 * 1024**3,
    )

    assert 1 <= capacity <= 64


def test_gpu_batch_capacity_counts_pending_and_stacked_host_inputs() -> None:
    class Device:
        def __init__(self, _index: int) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    fake = SimpleNamespace(
        cuda=SimpleNamespace(
            Device=Device,
            runtime=SimpleNamespace(memGetInfo=lambda: (8 * 1024**3, 8 * 1024**3)),
        )
    )
    backend = CupyFormulaBackend(device_index=0, memory_fraction=0.5, cupy_module=fake)
    pixels = 512 * 512
    bytes_per_window = pixels * (3 * 10 + 5)

    capacity = backend.batch_capacity(
        window_width=512,
        window_height=512,
        band_count=3,
        host_budget_bytes=bytes_per_window * 4,
    )

    assert capacity == 4


def test_windows_unicode_include_rewrite_only_changes_cupy_paths() -> None:
    source = Path("H:/中文项目/.venv/Lib/site-packages/cupy/_core/include")
    destination = Path("C:/Users/example/AppData/Local/WOMAP/cupy-include/14.1/include")
    options = (
        f"-I{source}/cupy/_cccl/cub",
        f"-I{source}",
        "-IC:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.6/include",
        "--std=c++17",
    )

    rewritten = formula_backends._rewrite_cupy_include_options(
        options,
        source,
        destination,
    )

    assert str(source) not in " ".join(rewritten)
    assert str(destination) in rewritten[0]
    assert rewritten[2:] == options[2:]


def test_probe_rejects_invalid_device_without_exposing_runtime_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = SimpleNamespace(cuda=SimpleNamespace(runtime=SimpleNamespace(getDeviceCount=lambda: 0)))
    monkeypatch.setattr(formula_backends.importlib, "import_module", lambda _name: fake)

    with pytest.raises(GpuBackendUnavailable, match="gpu_device_unavailable"):
        probe_cupy_runtime(1)


class FailingGpuBackend:
    name = "cupy"

    def __init__(self) -> None:
        self.calls = 0

    def batch_capacity(self, **_kwargs: object) -> int:
        return 2

    def evaluate_batch(
        self,
        _formula: FormulaNode,
        _data: np.ndarray,
        _masks: np.ndarray,
        _bands: list[int],
    ) -> FormulaBatchResult:
        self.calls += 1
        raise GpuBackendRuntimeError("gpu_oom")

    def release(self) -> None:
        return None


class WorkingGpuBackend:
    name = "cupy"

    def batch_capacity(self, **_kwargs: object) -> int:
        return 2

    def evaluate_batch(
        self,
        formula: FormulaNode,
        data: np.ndarray,
        masks: np.ndarray,
        bands: list[int],
    ) -> FormulaBatchResult:
        result = NumpyFormulaBackend().evaluate_batch(formula, data, masks, bands)
        return FormulaBatchResult(
            output=result.output,
            invalid_mask=result.invalid_mask,
            timings=FormulaBackendTimings(device_compute_ms=1),
        )

    def release(self) -> None:
        return None


def _write_source(path: Path) -> None:
    import rasterio
    from rasterio.transform import from_origin

    values = np.arange(64 * 64, dtype=np.float32).reshape(64, 64)
    values[0, 0] = -9999.0
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=64,
        height=64,
        count=1,
        dtype="float32",
        crs="EPSG:3857",
        transform=from_origin(0, 640, 10, 10),
        nodata=-9999.0,
    ) as dataset:
        dataset.write(values, 1)


def _gpu_decision() -> GpuExecutionDecision:
    return GpuExecutionDecision(
        requested_backend="auto",
        effective_backend="cupy",
        gate_status="passed",
        reason="test_gate_passed",
    )


def test_gpu_runtime_failure_restarts_entire_formula_on_cpu_and_opens_circuit(
    tmp_path: Path,
) -> None:
    reset_gpu_circuit_for_tests()
    storage = RasterStorage(str(tmp_path / "store"), str(tmp_path / "scratch"), 2)
    source = storage.root / "source.tif"
    _write_source(source)
    failing = FailingGpuBackend()
    processor = RasterProcessor(
        storage,
        _profile("auto"),
        gpu_decision=_gpu_decision(),
        formula_backend=failing,
    )

    result = processor.materialize_formula(
        source,
        "fallback",
        "a" * 64,
        _binary("+", _band(), _number(1.0)),
    )

    assert failing.calls == 1
    assert result.formula_execution is not None
    assert result.formula_execution.effective_backend == "cpu"
    assert result.formula_execution.gate_status == "fallback"
    assert result.formula_execution.fallback_reason == "gpu_oom"
    assert gpu_circuit_reason() == "gpu_oom"
    assert list(storage.scratch.iterdir()) == []
    reset_gpu_circuit_for_tests()


def test_gdal_io_error_does_not_masquerade_as_gpu_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rasterio.shutil

    reset_gpu_circuit_for_tests()
    storage = RasterStorage(str(tmp_path / "store"), str(tmp_path / "scratch"), 2)
    source = storage.root / "source.tif"
    _write_source(source)
    processor = RasterProcessor(
        storage,
        _profile("auto"),
        gpu_decision=_gpu_decision(),
        formula_backend=WorkingGpuBackend(),
    )
    monkeypatch.setattr(rasterio.shutil, "copy", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk")))

    with pytest.raises(OSError, match="disk"):
        processor.materialize_formula(source, "io-error", "b" * 64, _band())

    assert gpu_circuit_reason() is None
    assert list(storage.scratch.iterdir()) == []


def test_raster_job_formula_backend_contract_is_typed_and_filters_internal_fields() -> None:
    detail = RasterJobProgressDetail.model_validate(
        {
            "stage": "completed",
            "operation": "derive",
            "phase_timings_ms": {
                "preflight": 1,
                "compute": 20,
                "validation": 2,
                "total": 30,
                "backend_init": 3,
                "host_to_device": 4,
                "device_compute": 5,
                "device_to_host": 6,
            },
            "formula_backend": {
                "requested_backend": "auto",
                "effective_backend": "cpu",
                "gate_status": "fallback",
                "fallback_reason": "gpu_oom",
                "fallback_attempt_ms": 12,
                "max_batch_windows": 1,
                "lease_owner_hash": "private",
                "report_path": "C:/private/gate.json",
            },
        }
    )

    serialized = detail.model_dump(mode="json")
    assert serialized["formula_backend"]["fallback_reason"] == "gpu_oom"
    assert serialized["phase_timings_ms"]["device_compute"] == 5
    assert "lease_owner_hash" not in str(serialized)
    assert "report_path" not in str(serialized)
