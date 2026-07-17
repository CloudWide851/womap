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


class SystemCapability(BaseModel):
    platform: Literal["windows", "linux", "other"]
    release: str
    architecture: str
    cpu: CpuCapability
    memory: MemoryCapability
    storage: StorageCapability


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
