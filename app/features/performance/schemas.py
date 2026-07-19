from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.shared.config import ResolvedPerformanceSettings


CapabilityStatus = Literal["available", "unavailable", "restricted", "unknown"]


class CpuCapability(BaseModel):
    logical_cores: int = Field(ge=1)
    physical_cores: int | None = Field(default=None, ge=1)
    model: str | None = None


class MemoryCapability(BaseModel):
    total_bytes: int | None = Field(default=None, ge=0)
    available_bytes: int | None = Field(default=None, ge=0)


class StorageCapability(BaseModel):
    status: CapabilityStatus
    free_bytes: int | None = Field(default=None, ge=0)
    kind: Literal["ssd", "hdd", "network", "unknown"] = "unknown"


class PowerCapability(BaseModel):
    status: CapabilityStatus = "unknown"
    mode: Literal["balanced", "performance", "power_saver", "unknown"] = "unknown"


class SystemCapability(BaseModel):
    platform: Literal["windows", "linux", "other"]
    release: str
    architecture: str
    cpu: CpuCapability
    memory: MemoryCapability
    storage: StorageCapability
    power: PowerCapability = Field(default_factory=PowerCapability)


class GpuCapability(BaseModel):
    status: CapabilityStatus = "available"
    vendor: Literal["nvidia", "amd", "intel", "microsoft", "other", "unknown"]
    name: str
    driver: str | None = None
    memory_mib: int | None = Field(default=None, ge=0)
    compute_capability: str | None = None


class SoftwareCapability(BaseModel):
    status: CapabilityStatus
    version: str | None = None


class SoftwareCapabilities(BaseModel):
    python: SoftwareCapability
    rasterio: SoftwareCapability
    gdal: SoftwareCapability
    cupy: SoftwareCapability
    postgresql: SoftwareCapability
    postgis: SoftwareCapability
    redis: SoftwareCapability


class QueueCapability(BaseModel):
    status: CapabilityStatus
    queued: int | None = Field(default=None, ge=0)
    running: int | None = Field(default=None, ge=0)


class RuntimeCapability(BaseModel):
    mode: Literal["development", "production"]
    profile: ResolvedPerformanceSettings
    gpu_execution_enabled: bool = False
    gpu_execution_reason: str
    gpu_effective_backend: Literal["cpu", "cupy"] = "cpu"
    gpu_gate_status: Literal[
        "disabled", "unavailable", "missing", "rejected", "passed", "fallback"
    ] = "disabled"
    gpu_benchmark_speedup: float | None = Field(default=None, ge=0)


class PerformanceRecommendation(BaseModel):
    code: str = Field(pattern=r"^[a-z0-9_]{1,64}$")
    severity: Literal["info", "warning"]
    scope: Literal["process", "user", "system"]
    admin_required: bool = False
    evidence: str
    expected_effect: str
    action: str
    restore_action: str | None = None


class PerformanceCapabilityResponse(BaseModel):
    schema_version: Literal["womap.performance-capabilities/v1"] = (
        "womap.performance-capabilities/v1"
    )
    captured_at: datetime
    system: SystemCapability
    gpus: list[GpuCapability] = Field(default_factory=list)
    software: SoftwareCapabilities
    runtime: RuntimeCapability
    queue: QueueCapability
    recommendations: list[PerformanceRecommendation] = Field(default_factory=list)


class DatabasePoolMetric(BaseModel):
    active: int = Field(ge=0)
    peak: int = Field(ge=0)
    checkouts: int = Field(ge=0)
    timeouts: int = Field(ge=0)
    samples: int = Field(ge=0)
    wait_p50_ms: float = Field(ge=0)
    wait_p95_ms: float = Field(ge=0)
    wait_max_ms: float = Field(ge=0)


class DatabaseConnectionBudget(BaseModel):
    configured_connections: int = Field(ge=0)
    server_max_connections: int | None = Field(default=None, ge=1)
    reserved_connections: int | None = Field(default=None, ge=0)
    within_budget: bool | None = None


class CacheMetric(BaseModel):
    hit: int = Field(ge=0)
    miss: int = Field(ge=0)
    write: int = Field(ge=0)
    error: int = Field(ge=0)
    corruption: int = Field(ge=0)
    oversize: int = Field(ge=0)
    hit_rate: float = Field(ge=0, le=1)


class RangeMetric(BaseModel):
    requests: int = Field(ge=0)
    bytes: int = Field(ge=0)
    statuses: dict[str, int] = Field(default_factory=dict)


class PerformanceMetricsResponse(BaseModel):
    schema_version: Literal["womap.performance-metrics/v1"] = "womap.performance-metrics/v1"
    captured_at: datetime
    database_pools: dict[str, DatabasePoolMetric] = Field(default_factory=dict)
    connection_budget: DatabaseConnectionBudget
    cache: CacheMetric
    range: RangeMetric
