from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from threading import Lock
from typing import Any, Protocol

import numpy as np

from app.features.rasters.schemas import FormulaNode


FORMULA_GPU_CONTRACT_VERSION = "womap.raster-formula-gpu/v1"
FORMULA_NODATA = np.float32(-9999.0)
GPU_MEMORY_RESERVE_BYTES = 256 * 1024**2
GPU_MAX_BATCH_WINDOWS = 64
_CUPY_SETUP_LOCK = Lock()


def _milliseconds(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


class GpuBackendError(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class GpuBackendUnavailable(GpuBackendError):
    pass


class GpuBackendRuntimeError(GpuBackendError):
    pass


@dataclass(frozen=True)
class GpuRuntimeInfo:
    fingerprint: str
    device_index: int
    device_name: str
    compute_capability: str
    driver_version: str
    cuda_runtime_version: str
    cupy_version: str
    total_memory_bytes: int
    initialization_ms: int

    def public_fingerprint_fields(self) -> dict[str, str | int]:
        return {
            "contract_version": FORMULA_GPU_CONTRACT_VERSION,
            "device_index": self.device_index,
            "device_name": self.device_name,
            "compute_capability": self.compute_capability,
            "driver_version": self.driver_version,
            "cuda_runtime_version": self.cuda_runtime_version,
            "cupy_version": self.cupy_version,
        }


@dataclass
class FormulaBackendTimings:
    backend_init_ms: int = 0
    host_to_device_ms: int = 0
    device_compute_ms: int = 0
    device_to_host_ms: int = 0

    def add(self, other: FormulaBackendTimings) -> None:
        self.backend_init_ms += other.backend_init_ms
        self.host_to_device_ms += other.host_to_device_ms
        self.device_compute_ms += other.device_compute_ms
        self.device_to_host_ms += other.device_to_host_ms


@dataclass(frozen=True)
class FormulaBatchResult:
    output: np.ndarray
    invalid_mask: np.ndarray
    timings: FormulaBackendTimings


class FormulaArrayBackend(Protocol):
    name: str

    def batch_capacity(
        self,
        *,
        window_width: int,
        window_height: int,
        band_count: int,
        host_budget_bytes: int,
    ) -> int: ...

    def evaluate_batch(
        self,
        formula: FormulaNode,
        data: np.ndarray,
        masks: np.ndarray,
        bands: list[int],
    ) -> FormulaBatchResult: ...

    def release(self) -> None: ...


def evaluate_formula_ast(node: FormulaNode, bands: dict[int, Any], array_module: Any) -> Any:
    if node.kind == "band":
        if node.band is None or node.band not in bands:
            raise ValueError("公式引用的波段没有对应数组。")
        return bands[node.band]
    if node.kind == "number":
        if node.value is None:
            raise ValueError("公式常量无效。")
        return float(node.value)
    if node.kind == "unary":
        if node.argument is None:
            raise ValueError("公式一元节点无效。")
        value = evaluate_formula_ast(node.argument, bands, array_module)
        return value if node.operator == "+" else -value
    if node.kind == "binary":
        if node.left is None or node.right is None:
            raise ValueError("公式二元节点无效。")
        left = evaluate_formula_ast(node.left, bands, array_module)
        right = evaluate_formula_ast(node.right, bands, array_module)
        if node.operator == "+":
            return left + right
        if node.operator == "-":
            return left - right
        if node.operator == "*":
            return left * right
        if node.operator == "/":
            return left / right
        if node.operator == "^":
            return array_module.power(left, right)
        raise ValueError("不支持的公式运算符。")

    values = [evaluate_formula_ast(argument, bands, array_module) for argument in node.arguments]
    if node.name == "abs":
        return array_module.abs(values[0])
    if node.name == "sqrt":
        return array_module.sqrt(values[0])
    if node.name == "log":
        return array_module.log(values[0])
    if node.name == "min":
        return array_module.minimum(values[0], values[1])
    if node.name == "max":
        return array_module.maximum(values[0], values[1])
    if node.name == "clamp":
        return array_module.clip(values[0], values[1], values[2])
    raise ValueError("不支持的公式函数。")


def _validate_batch_inputs(data: np.ndarray, masks: np.ndarray, bands: list[int]) -> None:
    if data.ndim != 4 or masks.shape != data.shape:
        raise ValueError("公式批次数组形状无效。")
    if data.shape[1] != len(bands):
        raise ValueError("公式批次波段数量无效。")
    if data.dtype != np.float32:
        raise ValueError("公式批次必须使用 float32。")


class NumpyFormulaBackend:
    name = "cpu"

    def batch_capacity(
        self,
        *,
        window_width: int,
        window_height: int,
        band_count: int,
        host_budget_bytes: int,
    ) -> int:
        del window_width, window_height, band_count, host_budget_bytes
        return 1

    def evaluate_batch(
        self,
        formula: FormulaNode,
        data: np.ndarray,
        masks: np.ndarray,
        bands: list[int],
    ) -> FormulaBatchResult:
        _validate_batch_inputs(data, masks, bands)
        band_values = {band: data[:, index] for index, band in enumerate(bands)}
        input_invalid = np.any(masks, axis=1)
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            value = evaluate_formula_ast(formula, band_values, np)
            value_array = np.asarray(value, dtype=np.float32)
            if value_array.ndim == 0:
                value_array = np.broadcast_to(value_array, input_invalid.shape)
            else:
                value_array = np.broadcast_to(value_array, input_invalid.shape)
            invalid = ~np.isfinite(value_array) | input_invalid
            output = np.where(invalid, FORMULA_NODATA, value_array).astype(np.float32)
        return FormulaBatchResult(
            output=np.asarray(output, dtype=np.float32),
            invalid_mask=np.asarray(invalid, dtype=np.bool_),
            timings=FormulaBackendTimings(),
        )

    def release(self) -> None:
        return None


class CupyFormulaBackend:
    name = "cupy"

    def __init__(
        self,
        *,
        device_index: int,
        memory_fraction: float,
        cupy_module: Any | None = None,
    ) -> None:
        self.device_index = device_index
        self.memory_fraction = memory_fraction
        self._cupy = cupy_module
        self._pending_initialization_ms = 0

    def _load(self) -> Any:
        if self._cupy is not None:
            return self._cupy
        started = time.perf_counter()
        try:
            self._cupy = _load_cupy()
        except (ImportError, OSError) as exc:
            raise GpuBackendUnavailable("cupy_runtime_unavailable") from exc
        self._pending_initialization_ms += _milliseconds(started)
        return self._cupy

    def batch_capacity(
        self,
        *,
        window_width: int,
        window_height: int,
        band_count: int,
        host_budget_bytes: int,
    ) -> int:
        cp = self._load()
        try:
            with cp.cuda.Device(self.device_index):
                free_bytes, total_bytes = cp.cuda.runtime.memGetInfo()
        except Exception as exc:
            raise GpuBackendRuntimeError(_gpu_failure_reason(exc)) from exc

        pixels = max(1, window_width * window_height)
        input_bands = max(1, band_count)
        # Pending windows and np.stack briefly hold two copies of every input.
        # Account for float32 data, bool masks, float32 output and its bool mask.
        host_bytes_per_window = pixels * (input_bands * 10 + 5)
        device_bytes_per_window = pixels * (input_bands * 5 + 33)
        device_budget = min(
            int(total_bytes * self.memory_fraction),
            max(0, int(free_bytes) - GPU_MEMORY_RESERVE_BYTES),
        )
        host_capacity = host_budget_bytes // max(1, host_bytes_per_window)
        device_capacity = device_budget // max(1, device_bytes_per_window)
        capacity = min(GPU_MAX_BATCH_WINDOWS, host_capacity, device_capacity)
        if capacity < 1:
            raise GpuBackendRuntimeError("gpu_memory_budget_too_small")
        return capacity

    def evaluate_batch(
        self,
        formula: FormulaNode,
        data: np.ndarray,
        masks: np.ndarray,
        bands: list[int],
    ) -> FormulaBatchResult:
        _validate_batch_inputs(data, masks, bands)
        cp = self._load()
        timings = FormulaBackendTimings(backend_init_ms=self._pending_initialization_ms)
        self._pending_initialization_ms = 0
        device_data = device_masks = output = invalid = None
        try:
            with cp.cuda.Device(self.device_index):
                started = time.perf_counter()
                device_data = cp.asarray(data, dtype=cp.float32)
                device_masks = cp.asarray(masks, dtype=cp.bool_)
                cp.cuda.get_current_stream().synchronize()
                timings.host_to_device_ms = _milliseconds(started)

                started = time.perf_counter()
                band_values = {
                    band: device_data[:, index] for index, band in enumerate(bands)
                }
                input_invalid = cp.any(device_masks, axis=1)
                value = evaluate_formula_ast(formula, band_values, cp)
                value_array = cp.asarray(value, dtype=cp.float32)
                value_array = cp.broadcast_to(value_array, input_invalid.shape)
                invalid = ~cp.isfinite(value_array) | input_invalid
                output = cp.where(invalid, float(FORMULA_NODATA), value_array).astype(
                    cp.float32
                )
                cp.cuda.get_current_stream().synchronize()
                timings.device_compute_ms = _milliseconds(started)

                started = time.perf_counter()
                host_output = cp.asnumpy(output)
                host_invalid = cp.asnumpy(invalid)
                cp.cuda.get_current_stream().synchronize()
                timings.device_to_host_ms = _milliseconds(started)
        except GpuBackendError:
            raise
        except Exception as exc:
            raise GpuBackendRuntimeError(_gpu_failure_reason(exc)) from exc
        finally:
            del device_data, device_masks, output, invalid

        return FormulaBatchResult(
            output=np.asarray(host_output, dtype=np.float32),
            invalid_mask=np.asarray(host_invalid, dtype=np.bool_),
            timings=timings,
        )

    def release(self) -> None:
        if self._cupy is None:
            return
        try:
            with self._cupy.cuda.Device(self.device_index):
                self._cupy.get_default_memory_pool().free_all_blocks()
                self._cupy.get_default_pinned_memory_pool().free_all_blocks()
        except Exception:
            return


def probe_cupy_runtime(device_index: int) -> GpuRuntimeInfo:
    started = time.perf_counter()
    try:
        cp = _load_cupy()
    except (ImportError, OSError) as exc:
        raise GpuBackendUnavailable("cupy_runtime_unavailable") from exc

    try:
        device_count = int(cp.cuda.runtime.getDeviceCount())
        if device_index >= device_count:
            raise GpuBackendUnavailable("gpu_device_unavailable")
        with cp.cuda.Device(device_index):
            properties = cp.cuda.runtime.getDeviceProperties(device_index)
            probe = cp.asarray([1.0], dtype=cp.float32)
            probe = probe * np.float32(2.0)
            cp.cuda.get_current_stream().synchronize()
            if float(cp.asnumpy(probe)[0]) != 2.0:
                raise GpuBackendRuntimeError("gpu_probe_failed")
            free_bytes, total_memory_bytes = cp.cuda.runtime.memGetInfo()
            del probe
            cp.get_default_memory_pool().free_all_blocks()
    except GpuBackendError:
        raise
    except Exception as exc:
        raise GpuBackendRuntimeError(_gpu_failure_reason(exc)) from exc

    name_value = properties.get("name", "unknown")
    if isinstance(name_value, bytes):
        name_value = name_value.decode("utf-8", errors="replace")
    device_name = " ".join(str(name_value).split())[:120] or "unknown"
    compute_capability = f"{int(properties.get('major', 0))}.{int(properties.get('minor', 0))}"
    driver_version = str(int(cp.cuda.runtime.driverGetVersion()))
    runtime_version = str(int(cp.cuda.runtime.runtimeGetVersion()))
    cupy_version = str(getattr(cp, "__version__", "unknown"))[:40]
    fields = {
        "contract_version": FORMULA_GPU_CONTRACT_VERSION,
        "device_index": device_index,
        "device_name": device_name,
        "compute_capability": compute_capability,
        "driver_version": driver_version,
        "cuda_runtime_version": runtime_version,
        "cupy_version": cupy_version,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return GpuRuntimeInfo(
        fingerprint=fingerprint,
        device_index=device_index,
        device_name=device_name,
        compute_capability=compute_capability,
        driver_version=driver_version,
        cuda_runtime_version=runtime_version,
        cupy_version=cupy_version,
        total_memory_bytes=int(total_memory_bytes or free_bytes),
        initialization_ms=_milliseconds(started),
    )


def _gpu_failure_reason(exc: Exception) -> str:
    name = type(exc).__name__.casefold()
    if "outofmemory" in name or "memoryallocation" in name:
        return "gpu_oom"
    return "gpu_runtime_error"


def _load_cupy() -> Any:
    _prepare_cupy_cache()
    cp = importlib.import_module("cupy")
    try:
        _configure_windows_unicode_include(cp)
    except GpuBackendError:
        raise
    except Exception as exc:
        raise GpuBackendUnavailable("cupy_runtime_unavailable") from exc
    return cp


def _prepare_cupy_cache() -> None:
    if os.environ.get("CUPY_CACHE_DIR"):
        return
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data or not local_app_data.isascii():
        return
    cache = Path(local_app_data) / "WOMAP" / "cupy-cache"
    try:
        cache.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    os.environ["CUPY_CACHE_DIR"] = str(cache)


def _configure_windows_unicode_include(cp: Any) -> None:
    if sys.platform != "win32" or not getattr(cp, "__file__", None):
        return
    source = (Path(cp.__file__).resolve().parent / "_core" / "include").resolve()
    if str(source).isascii():
        return
    local_app_data = os.environ.get("LOCALAPPDATA")
    version = str(getattr(cp, "__version__", "unknown"))
    if not local_app_data or not local_app_data.isascii() or not version.replace(".", "").isdigit():
        raise GpuBackendUnavailable("gpu_ascii_include_cache_unavailable")
    destination = (
        Path(local_app_data) / "WOMAP" / "cupy-include" / version / "include"
    ).resolve()
    if not str(destination).isascii():
        raise GpuBackendUnavailable("gpu_ascii_include_cache_unavailable")

    with _CUPY_SETUP_LOCK:
        marker = destination / ".womap-complete"
        if not marker.is_file():
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source, destination, dirs_exist_ok=True)
                marker.write_text(FORMULA_GPU_CONTRACT_VERSION, encoding="ascii")
            except OSError as exc:
                raise GpuBackendUnavailable("gpu_ascii_include_cache_unavailable") from exc
        compiler = importlib.import_module("cupy.cuda.compiler")
        original = compiler._compile_module_with_cache
        if getattr(original, "__womap_unicode_include_patch__", False):
            return

        @wraps(original)
        def compile_with_ascii_include(source_code: str, options: tuple[str, ...], *args, **kwargs):
            safe_options = _rewrite_cupy_include_options(options, source, destination)
            return original(source_code, safe_options, *args, **kwargs)

        compile_with_ascii_include.__womap_unicode_include_patch__ = True
        compiler._compile_module_with_cache = compile_with_ascii_include


def _rewrite_cupy_include_options(
    options: tuple[str, ...],
    source: Path,
    destination: Path,
) -> tuple[str, ...]:
    unicode_root = str(source)
    ascii_root = str(destination)
    return tuple(
        option.replace(unicode_root, ascii_root) if option.startswith("-I") else option
        for option in options
    )
