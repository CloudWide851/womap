from __future__ import annotations

import json
from collections import OrderedDict
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.exports.schemas import ExportFeature, ExportLayer
from app.features.jobs.execution import apply_job_lifecycle, assert_job_execution
from app.features.jobs.policies import new_job_runtime_fields
from app.features.jobs.repository import JobRepository
from app.features.jobs.schemas import JobStatus, VectorExportJobProgressDetail
from app.models.job import Job
from app.models.layer import Layer
from app.models.map_feature import MapFeature


class ExportRepository:
    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session

    async def list_layers_for_export(self, layer_ids: list[int]) -> list[ExportLayer]:
        if self.session is None or not layer_ids:
            return []

        stmt = (
            select(
                Layer.id.label("layer_id"),
                Layer.name.label("layer_name"),
                Layer.geometry_type,
                Layer.crs,
                MapFeature.id.label("feature_id"),
                MapFeature.properties,
                func.ST_AsGeoJSON(MapFeature.geom).label("geometry_json"),
            )
            .join(MapFeature, MapFeature.layer_id == Layer.id)
            .where(Layer.id.in_(layer_ids))
            .order_by(Layer.id, MapFeature.id)
        )
        rows = (await self.session.execute(stmt)).mappings().all()
        grouped: OrderedDict[int, ExportLayer] = OrderedDict()

        for row in rows:
            geometry = self._parse_geometry(row["geometry_json"])
            if geometry is None:
                continue

            layer_id = int(row["layer_id"])
            if layer_id not in grouped:
                grouped[layer_id] = ExportLayer(
                    id=layer_id,
                    name=str(row["layer_name"]),
                    geometry_type=str(row["geometry_type"]),
                    crs=row["crs"] or "EPSG:3857",
                    features=[],
                )

            grouped[layer_id].features.append(
                ExportFeature(
                    id=int(row["feature_id"]),
                    geometry=geometry,
                    properties=dict(row["properties"] or {}),
                ),
            )

        return [layer for layer in grouped.values() if layer.features]

    async def raster_layer_ids(self, layer_ids: list[int]) -> list[int]:
        if self.session is None or not layer_ids:
            return []
        values = await self.session.scalars(
            select(Layer.id).where(
                Layer.id.in_(layer_ids),
                Layer.geometry_type == "Raster",
            )
        )
        return [int(value) for value in values]

    async def validate_export_layers(self, layer_ids: list[int]) -> None:
        if self.session is None:
            raise RuntimeError("导出数据库会话不可用。")
        selected = set(layer_ids)
        rows = (
            await self.session.execute(
                select(Layer.id, Layer.geometry_type, Layer.feature_count).where(
                    Layer.id.in_(layer_ids)
                )
            )
        ).all()
        if any(row.geometry_type == "Raster" for row in rows):
            raise ValueError("SHP/GDB 仅支持矢量图层；请从栅格导出入口导出 COG。")
        available = {int(row.id) for row in rows if int(row.feature_count or 0) > 0}
        if available != selected:
            raise LookupError("没有找到可导出的后端图层或图斑。")

    async def create_job(self, format_name: str, layer_ids: list[int]) -> JobStatus:
        detail = VectorExportJobProgressDetail(total_layers=len(layer_ids))
        job = Job(
            id=f"vector-export-{uuid4().hex}",
            job_type="vector-export",
            status="queued",
            progress=0,
            message="矢量成果导出已进入队列。",
            payload={"format": format_name, "layer_ids": layer_ids},
            result={"detail": detail.model_dump(mode="json")},
            **new_job_runtime_fields("vector-export"),
        )
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return JobRepository.to_status(job)

    async def get_job(self, job_id: str) -> Job | None:
        if self.session is None:
            return None
        return await self.session.get(Job, job_id)

    async def update_job(
        self,
        job: Job,
        *,
        status: str | None = None,
        progress: int | None = None,
        message: str | None = None,
        detail: VectorExportJobProgressDetail | None = None,
        extra_result: dict[str, Any] | None = None,
    ) -> None:
        if self.session is None:
            raise RuntimeError("导出数据库会话不可用。")
        await assert_job_execution(self.session, job)
        apply_job_lifecycle(job, status)
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

    async def rollback(self) -> None:
        if self.session is not None:
            await self.session.rollback()

    def _parse_geometry(self, value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        if isinstance(value, str):
            parsed = json.loads(value)
        else:
            parsed = value
        if not isinstance(parsed, dict):
            return None
        return parsed
