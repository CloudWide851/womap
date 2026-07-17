from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.performance.detectors import CapabilityDetector
from app.features.performance.schemas import (
    GpuCapability,
    PerformanceCapabilityResponse,
    PerformanceRecommendation,
    QueueCapability,
    RuntimeCapability,
    SoftwareCapabilities,
    SoftwareCapability,
)
from app.models.job import Job
from app.shared.config import ROOT_DIR, Settings, get_settings


class PerformanceService:
    def __init__(
        self,
        session: AsyncSession | None = None,
        *,
        detector: CapabilityDetector | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.detector = detector or CapabilityDetector()
        self.settings = settings or get_settings()

    async def get_capabilities(self) -> PerformanceCapabilityResponse:
        storage_path = self._managed_storage_path()
        system_task = asyncio.to_thread(self.detector.detect_system, storage_path)
        gpu_task = asyncio.to_thread(self.detector.detect_gpus)
        software_task = asyncio.to_thread(self.detector.detect_local_software)
        database_task = self._database_capabilities()
        redis_task = self._redis_capability()

        system, gpus, local_software, database, redis = await asyncio.gather(
            system_task,
            gpu_task,
            software_task,
            database_task,
            redis_task,
        )
        postgresql, postgis, queue = database
        resolved = self.settings.performance.resolve(
            logical_cpu_count=system.cpu.logical_cores,
            total_memory_bytes=system.memory.total_bytes,
        )
        gpu_reason = self._gpu_execution_reason(gpus, local_software["cupy"])

        return PerformanceCapabilityResponse(
            captured_at=datetime.now(timezone.utc),
            system=system,
            gpus=gpus,
            software=SoftwareCapabilities(
                python=local_software["python"],
                rasterio=local_software["rasterio"],
                gdal=local_software["gdal"],
                cupy=local_software["cupy"],
                postgresql=postgresql,
                postgis=postgis,
                redis=redis,
            ),
            runtime=RuntimeCapability(
                mode=self.settings.runtime.mode,
                profile=resolved,
                gpu_execution_enabled=False,
                gpu_execution_reason=gpu_reason,
            ),
            queue=queue,
            recommendations=self._recommendations(
                system.memory.available_bytes,
                bool(gpus),
                local_software["cupy"],
                redis,
            ),
        )

    def _managed_storage_path(self) -> Path:
        configured = Path(self.settings.imports.raster_scratch_path)
        return configured if configured.is_absolute() else ROOT_DIR / configured

    async def _database_capabilities(
        self,
    ) -> tuple[SoftwareCapability, SoftwareCapability, QueueCapability]:
        if self.session is None:
            return (
                SoftwareCapability(status="unknown"),
                SoftwareCapability(status="unknown"),
                QueueCapability(status="unknown"),
            )
        postgresql = SoftwareCapability(status="unavailable")
        postgis = SoftwareCapability(status="unavailable")
        queue = QueueCapability(status="unknown")
        try:
            if self.settings.database.uses_postgis:
                async with asyncio.timeout(2.0):
                    row = (
                        await self.session.execute(
                            text(
                                "SELECT current_setting('server_version') AS postgresql_version, "
                                "postgis_version() AS postgis_version"
                            )
                        )
                    ).mappings().one()
                postgresql = SoftwareCapability(
                    status="available", version=self._safe_version(row["postgresql_version"])
                )
                postgis = SoftwareCapability(
                    status="available", version=self._safe_version(row["postgis_version"])
                )
            else:
                postgresql = SoftwareCapability(status="unavailable")
                postgis = SoftwareCapability(status="unavailable")

            async with asyncio.timeout(2.0):
                queued = await self.session.scalar(
                    select(func.count()).select_from(Job).where(Job.status == "queued")
                )
                running = await self.session.scalar(
                    select(func.count()).select_from(Job).where(Job.status == "running")
                )
            queue = QueueCapability(
                status="available",
                queued=int(queued or 0),
                running=int(running or 0),
            )
        except Exception:
            # Infrastructure errors are deliberately collapsed to status values.
            pass
        return postgresql, postgis, queue

    async def _redis_capability(self) -> SoftwareCapability:
        if not self.settings.redis.configured:
            return SoftwareCapability(status="unavailable")
        client: Redis | None = None
        try:
            client = Redis(**self.settings.redis.connection_kwargs())
            async with asyncio.timeout(2.0):
                if not await client.ping():
                    return SoftwareCapability(status="unavailable")
                information: dict[str, Any] = await client.info(section="server")
            return SoftwareCapability(
                status="available",
                version=self._safe_version(information.get("redis_version")),
            )
        except Exception:
            return SoftwareCapability(status="unavailable")
        finally:
            if client is not None:
                try:
                    await client.aclose()
                except Exception:
                    # Probe cleanup must not turn an unavailable Redis into a failed API response.
                    pass

    def _gpu_execution_reason(
        self,
        gpus: list[GpuCapability],
        cupy: SoftwareCapability,
    ) -> str:
        requested = self.settings.performance.gpu.backend
        if not gpus:
            return "no_gpu_detected"
        if requested == "cpu":
            return "cpu_backend_is_default"
        if cupy.status != "available":
            return "cupy_runtime_unavailable"
        return "local_correctness_and_speedup_gate_pending"

    @staticmethod
    def _recommendations(
        available_memory: int | None,
        has_gpu: bool,
        cupy: SoftwareCapability,
        redis: SoftwareCapability,
    ) -> list[PerformanceRecommendation]:
        recommendations = [
            PerformanceRecommendation(
                code="global_os_settings_advisory_only",
                severity="info",
                scope="system",
                evidence="WOMAP 当前只读探测系统状态。",
                expected_effect="避免启动或升级意外改变整机行为。",
                action="仅在后续诊断明确给出影响和恢复步骤后，由用户显式执行系统级调整。",
            )
        ]
        if available_memory is not None and available_memory < 4 * 1024**3:
            recommendations.append(
                PerformanceRecommendation(
                    code="low_available_memory",
                    severity="warning",
                    scope="process",
                    evidence="可用内存低于 4 GiB。",
                    expected_effect="减少重任务与地图浏览争用，降低换页抖动。",
                    action="保持 low 档位并避免同时运行多个栅格或空间分析任务。",
                )
            )
        if has_gpu and cupy.status != "available":
            recommendations.append(
                PerformanceRecommendation(
                    code="gpu_render_only",
                    severity="info",
                    scope="user",
                    evidence="检测到 GPU，但可选 CuPy 计算运行时不可用。",
                    expected_effect="浏览器仍可使用 WebGL；后端计算保持可靠 CPU 路径。",
                    action="无需为普通地图浏览安装 CUDA；GPU 计算将在独立 PoC 门槛通过后开放。",
                )
            )
        if redis.status != "available":
            recommendations.append(
                PerformanceRecommendation(
                    code="redis_optional_unavailable",
                    severity="info",
                    scope="process",
                    evidence="Redis 当前不可用或未响应。",
                    expected_effect="不影响核心 GIS 流程；后续有界缓存命中率将无法采集。",
                    action="需要缓存基准时再启动 Redis，当前无需扩大缓存或绕过失效规则。",
                )
            )
        return recommendations

    @staticmethod
    def _safe_version(value: object) -> str | None:
        if value is None:
            return None
        normalized = " ".join(str(value).split())
        if any(marker in normalized.casefold() for marker in ("password", "token", "\\", "/home/")):
            return None
        return normalized[:120] or None
