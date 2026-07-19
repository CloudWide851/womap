from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.features.performance.detectors import CapabilityDetector
from app.features.performance.router import get_performance_service
from app.features.performance.schemas import (
    CpuCapability,
    GpuCapability,
    MemoryCapability,
    SoftwareCapability,
    StorageCapability,
    SystemCapability,
)
from app.features.performance.service import PerformanceService
from app.features.rasters.gpu_gate import GpuExecutionDecision
from app.main import create_app
from app.shared.config import PerformanceSettings, Settings
from conftest import allow_test_auth


GIB = 1024**3


def test_performance_profile_resolution_is_conservative_and_capped() -> None:
    limited = PerformanceSettings().resolve(
        logical_cpu_count=2,
        total_memory_bytes=4 * GIB,
    )
    assert limited.resolved_profile == "low"
    assert limited.gdal_threads == 1
    assert limited.gdal_cache_mib == 128
    assert limited.worker_concurrency == 1
    assert limited.enforcement == "active"

    workstation = PerformanceSettings().resolve(
        logical_cpu_count=128,
        total_memory_bytes=512 * GIB,
    )
    assert workstation.resolved_profile == "high"
    assert workstation.gdal_threads == 8
    assert workstation.gdal_cache_mib == 1024
    assert workstation.database_pool_size == 12
    assert workstation.worker_concurrency == 1


def test_performance_profile_allows_bounded_explicit_overrides() -> None:
    configured = PerformanceSettings.model_validate(
        {
            "profile": "balanced",
            "api": {"database_pool_size": 6, "database_max_overflow": 0},
            "gdal": {"cache_mib": 320, "thread_cap": 3},
            "browser": {"webgl_texture_cache": 192},
            "gpu": {"backend": "auto", "minimum_speedup": 1.75},
        }
    ).resolve(logical_cpu_count=16, total_memory_bytes=64 * GIB)

    assert configured.resolved_profile == "balanced"
    assert configured.resolution_reason == "explicit_profile"
    assert configured.database_pool_size == 6
    assert configured.database_max_overflow == 0
    assert configured.gdal_cache_mib == 320
    assert configured.gdal_threads == 3
    assert configured.webgl_texture_cache == 192
    assert configured.gpu_requested_backend == "auto"
    assert configured.gpu_minimum_speedup == 1.75

    constrained_high = PerformanceSettings(profile="high").resolve(
        logical_cpu_count=1,
        total_memory_bytes=4 * GIB,
    )
    assert constrained_high.gdal_threads == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"profile": "unbounded"},
        {"gdal": {"thread_cap": 0}},
        {"gdal": {"cache_mib": 8192}},
        {"gpu": {"memory_fraction": 1.0}},
        {"browser": {"vector_limit": 5001}},
    ],
)
def test_performance_profile_rejects_unsafe_values(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PerformanceSettings.model_validate(payload)


def test_missing_performance_sections_keep_backward_compatible_defaults() -> None:
    settings = Settings.model_validate({"performance": {"max_features_per_request": 4000}})

    assert settings.runtime.mode == "development"
    assert settings.performance.profile == "auto"
    assert settings.performance.max_features_per_request == 4000
    assert settings.performance.gpu.backend == "cpu"
    assert settings.performance.worker.enabled is False


def test_windows_detector_uses_allowlisted_fields_and_redacts_extra_values(tmp_path: Path) -> None:
    private_path = r"C:\Users\private-user\device.txt"

    def runner(arguments: list[str] | tuple[str, ...], _: float) -> str | None:
        command = " ".join(arguments)
        if "Win32_Processor" in command:
            return json.dumps(
                {
                    "cpu_name": "Example CPU",
                    "physical_cores": 8,
                    "total_memory": 32 * GIB,
                    "available_memory": 20 * GIB,
                    "serial_number": "private-serial",
                    "path": private_path,
                }
            )
        if "Win32_VideoController" in command:
            return json.dumps(
                {
                    "Name": "NVIDIA Example GPU",
                    "DriverVersion": "555.1",
                    "AdapterRAM": 8 * GIB,
                    "PNPDeviceID": "private-device-id",
                    "InstallPath": private_path,
                }
            )
        if "nvidia-smi" in command:
            return "NVIDIA Example GPU, 556.2, 12288, 8.6"
        return None

    detector = CapabilityDetector(command_runner=runner, platform_name="win32")
    system = detector.detect_system(tmp_path)
    gpus = detector.detect_gpus()
    serialized = json.dumps(
        {"system": system.model_dump(), "gpus": [gpu.model_dump() for gpu in gpus]}
    )

    assert system.platform == "windows"
    assert system.cpu.physical_cores == 8
    assert system.memory.total_bytes == 32 * GIB
    assert gpus[0].vendor == "nvidia"
    assert gpus[0].memory_mib == 12288
    assert gpus[0].compute_capability == "8.6"
    assert "private-serial" not in serialized
    assert "private-device-id" not in serialized
    assert private_path not in serialized


def test_detector_command_failure_and_timeout_degrade_without_exception(tmp_path: Path) -> None:
    detector = CapabilityDetector(
        command_runner=lambda _arguments, _timeout: None,
        platform_name="win32",
    )

    system = detector.detect_system(tmp_path)

    assert system.cpu.logical_cores >= 1
    assert system.cpu.physical_cores is None or system.cpu.physical_cores >= 1
    assert detector.detect_gpus() == []


class FakeDetector(CapabilityDetector):
    def detect_system(self, _storage_path: Path) -> SystemCapability:
        return SystemCapability(
            platform="windows",
            release="11",
            architecture="AMD64",
            cpu=CpuCapability(logical_cores=16, physical_cores=8, model="Example CPU"),
            memory=MemoryCapability(total_bytes=32 * GIB, available_bytes=20 * GIB),
            storage=StorageCapability(status="available", free_bytes=100 * GIB),
        )

    def detect_gpus(self) -> list[GpuCapability]:
        return [GpuCapability(vendor="nvidia", name="Example GPU", driver="555.1")]

    @staticmethod
    def detect_local_software() -> dict[str, SoftwareCapability]:
        return {
            "python": SoftwareCapability(status="available", version="3.12"),
            "rasterio": SoftwareCapability(status="available", version="1.4"),
            "gdal": SoftwareCapability(status="available", version="3.10"),
            "cupy": SoftwareCapability(status="available", version="14.1"),
        }


@pytest.mark.asyncio
async def test_capability_service_keeps_gpu_execution_behind_benchmark_gate() -> None:
    settings = Settings.model_validate(
        {
            "redis": {"host": ""},
            "performance": {"gpu": {"backend": "auto"}},
        }
    )
    response = await PerformanceService(
        detector=FakeDetector(),
        settings=settings,
        gpu_resolver=lambda _profile: GpuExecutionDecision(
            requested_backend="auto",
            effective_backend="cpu",
            gate_status="missing",
            reason="local_gpu_benchmark_missing",
        ),
    ).get_capabilities()

    assert response.runtime.profile.resolved_profile == "high"
    assert response.runtime.gpu_execution_enabled is False
    assert response.runtime.gpu_execution_reason == "local_gpu_benchmark_missing"
    assert response.runtime.gpu_effective_backend == "cpu"
    assert response.runtime.gpu_gate_status == "missing"
    assert response.runtime.gpu_benchmark_speedup is None
    assert response.software.postgresql.status == "unknown"
    assert response.queue.status == "unknown"
    assert "password" not in response.model_dump_json().casefold()


def test_performance_capability_route_is_authenticated_and_redacted() -> None:
    settings = Settings.model_validate({"redis": {"host": ""}})
    service = PerformanceService(detector=FakeDetector(), settings=settings)

    public_app = create_app()
    assert TestClient(public_app).get("/api/v1/performance/capabilities").status_code == 401

    protected_app = allow_test_auth(create_app())
    protected_app.dependency_overrides[get_performance_service] = lambda: service
    response = TestClient(protected_app).get("/api/v1/performance/capabilities")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "womap.performance-capabilities/v1"
    assert body["runtime"]["profile"]["enforcement"] == "active"
    assert body["runtime"]["gpu_execution_enabled"] is False
    assert body["runtime"]["gpu_effective_backend"] == "cpu"
    assert body["runtime"]["gpu_gate_status"] == "disabled"
    assert body["runtime"]["gpu_benchmark_speedup"] is None
    assert "local_config_path" not in response.text
    assert "gpu_fingerprint" not in response.text
    assert "gpu-gates" not in response.text
    assert "password" not in response.text.casefold()


def test_performance_metrics_route_is_authenticated_and_aggregate_only() -> None:
    settings = Settings.model_validate({"redis": {"host": ""}})
    service = PerformanceService(detector=FakeDetector(), settings=settings)

    public_app = create_app()
    assert TestClient(public_app).get("/api/v1/performance/metrics").status_code == 401

    protected_app = allow_test_auth(create_app())
    protected_app.dependency_overrides[get_performance_service] = lambda: service
    response = TestClient(protected_app).get("/api/v1/performance/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "womap.performance-metrics/v1"
    assert set(body) == {
        "schema_version",
        "captured_at",
        "database_pools",
        "connection_budget",
        "cache",
        "range",
    }
    assert "redis" not in response.text.casefold()
    assert "sql" not in response.text.casefold()
    assert "password" not in response.text.casefold()
