from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.jobs.repository import JobRepository
from app.features.jobs.schemas import (
    JobStatus,
    RasterExportJobProgressDetail,
    RasterJobProgressDetail,
)
from app.features.layers.repository import LayerRepository
from app.features.layers.schemas import LayerSummary
from app.features.projects.repository import ProjectRepository
from app.features.rasters.schemas import RasterStyle
from app.models.job import Job
from app.models.layer import Layer


class RasterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_layer(self, layer_id: int) -> Layer | None:
        return await self.session.get(Layer, layer_id)

    async def require_raster_layer(self, layer_id: int, *, visible: bool = False) -> Layer:
        layer = await self.get_layer(layer_id)
        if layer is None or layer.geometry_type != "Raster":
            raise KeyError(layer_id)
        if visible and not layer.visible:
            raise ValueError("栅格图层当前不可见，不能读取资产。")
        return layer

    async def raster_layers(self, layer_ids: list[int]) -> list[Layer]:
        layers = (
            await self.session.scalars(
                select(Layer).where(Layer.id.in_(layer_ids)).order_by(Layer.id)
            )
        ).all()
        if len(layers) != len(set(layer_ids)) or any(layer.geometry_type != "Raster" for layer in layers):
            raise ValueError("导出列表包含不存在或非栅格图层。")
        return list(layers)

    async def referenced_asset_paths(self) -> set[str]:
        values = (
            await self.session.scalars(
                select(Layer.data_path).where(
                    Layer.geometry_type == "Raster", Layer.data_path.is_not(None)
                )
            )
        ).all()
        return {str(value) for value in values if value}

    async def update_style(self, layer: Layer, style: RasterStyle) -> LayerSummary:
        layer.style = {**dict(layer.style or {}), "raster": style.model_dump(mode="json")}
        await self.session.commit()
        await self.session.refresh(layer)
        return LayerRepository.to_summary(layer)
    async def create_process_job(
        self,
        *,
        layer_id: int,
        payload: dict[str, Any],
    ) -> JobStatus:
        detail = RasterJobProgressDetail(
            operation="derive",
            layer_id=layer_id,
        )
        job = Job(
            id=f"raster-derive-{uuid4().hex}",
            job_type="raster-derive",
            status="queued",
            progress=0,
            message="派生栅格任务已进入队列。",
            payload={"layer_id": layer_id, **payload},
            result={"detail": detail.model_dump(mode="json")},
        )
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return JobRepository.to_status(job)

    async def create_export_job(self, layer_ids: list[int], format_name: str) -> JobStatus:
        detail = RasterExportJobProgressDetail(total_layers=len(layer_ids))
        job = Job(
            id=f"raster-export-{uuid4().hex}",
            job_type="raster-export",
            status="queued",
            progress=0,
            message="栅格导出任务已进入队列。",
            payload={"layer_ids": layer_ids, "format": format_name},
            result={"detail": detail.model_dump(mode="json")},
        )
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return JobRepository.to_status(job)

    async def get_job(self, job_id: str) -> Job | None:
        return await self.session.get(Job, job_id)

    async def update_job(
        self,
        job: Job,
        *,
        status: str | None = None,
        progress: int | None = None,
        message: str | None = None,
        detail: RasterJobProgressDetail | RasterExportJobProgressDetail | None = None,
        extra_result: dict[str, Any] | None = None,
    ) -> None:
        if status is not None:
            job.status = status
        if progress is not None:
            job.progress = max(0, min(100, progress))
        if message is not None:
            job.message = message
        result = dict(job.result or {})
        if detail is not None:
            result["detail"] = detail.model_dump(mode="json")
        if extra_result:
            result.update(extra_result)
        job.result = result
        await self.session.commit()

    async def create_derived_layer(
        self,
        *,
        name: str,
        asset_path: str,
        metadata: dict,
        bounds: dict[str, float],
        fingerprint: str,
        source_layer_id: int,
        style: RasterStyle | None,
    ) -> LayerSummary:
        project = await ProjectRepository(self.session).ensure_default_project()
        resolved_style = style or RasterStyle()
        layer = Layer(
            project_id=project.id,
            name=name,
            source_type="raster-derived",
            geometry_type="Raster",
            feature_count=0,
            crs="EPSG:3857",
            bounds=bounds,
            style={"raster": resolved_style.model_dump(mode="json")},
            fields=[],
            performance={
                "dataset_id": f"derived:{fingerprint[:24]}",
                "fingerprint": fingerprint,
                "source_layer_id": source_layer_id,
                "raster": metadata,
            },
            data_path=asset_path,
            visible=True,
            locked=True,
            opacity=1.0,
        )
        self.session.add(layer)
        await self.session.commit()
        await self.session.refresh(layer)
        return LayerRepository.to_summary(layer)
