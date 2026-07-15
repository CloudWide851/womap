from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.imports.schemas import CatalogDataset
from app.features.jobs.repository import JobRepository
from app.features.jobs.schemas import JobProgressDetail, JobStatus
from app.features.projects.repository import ProjectRepository
from app.models.job import Job
from app.models.layer import Layer
from app.models.map_feature import MapFeature


class ImportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_job(self, job_type: str, source_id: str, payload: dict[str, Any]) -> JobStatus:
        if await self.has_active_job(source_id):
            raise RuntimeError("该数据源已有同步或导入任务正在执行。")
        job = Job(
            id=f"{job_type}-{uuid4().hex}",
            job_type=job_type,
            status="queued",
            progress=0,
            message="任务已进入队列。",
            payload={"source_id": source_id, **payload},
            result={"detail": JobProgressDetail(source_id=source_id).model_dump()},
        )
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return JobRepository.to_status(job)

    async def has_active_job(self, source_id: str) -> bool:
        jobs = (
            await self.session.scalars(
                select(Job).where(Job.status.in_(["queued", "running"]))
            )
        ).all()
        return any((job.payload or {}).get("source_id") == source_id for job in jobs)

    async def get_job(self, job_id: str) -> Job | None:
        return await self.session.get(Job, job_id)

    async def update_job(
        self,
        job: Job,
        *,
        status: str | None = None,
        progress: int | None = None,
        message: str | None = None,
        detail: JobProgressDetail | None = None,
        extra_result: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> None:
        if status is not None:
            job.status = status
        if progress is not None:
            job.progress = max(0, min(100, progress))
        if message is not None:
            job.message = message
        result = dict(job.result or {})
        if detail is not None:
            result["detail"] = detail.model_dump()
        if extra_result:
            result.update(extra_result)
        job.result = result
        if commit:
            await self.session.commit()

    async def find_resumable_job(self, source_id: str, dataset_id: str) -> Job | None:
        jobs = (
            await self.session.scalars(
                select(Job)
                .where(Job.status.in_(["interrupted", "failed"]))
                .order_by(Job.updated_at.desc())
            )
        ).all()
        for job in jobs:
            payload = job.payload or {}
            completed = set((job.result or {}).get("completed_dataset_ids") or [])
            if (
                payload.get("source_id") == source_id
                and dataset_id in payload.get("dataset_ids", [])
                and dataset_id not in completed
            ):
                return job
        return None

    async def rollback(self) -> None:
        await self.session.rollback()

    async def imported_layers(self, source_id: str) -> list[Layer]:
        layers = (await self.session.scalars(select(Layer))).all()
        return [
            layer
            for layer in layers
            if (layer.performance or {}).get("source_id") == source_id
            and not (layer.performance or {}).get("staging", False)
        ]

    async def create_staging_layer(self, dataset: CatalogDataset, job_id: str) -> Layer:
        project = await ProjectRepository(self.session).ensure_default_project()
        style_colors = ["#4656a8", "#b45f4d", "#5b6f91", "#8a6d3b", "#725a9f"]
        layer = Layer(
            project_id=project.id,
            name=dataset.layer_name,
            source_type=dataset.format,
            geometry_type=dataset.geometry_type,
            feature_count=0,
            crs="EPSG:3857",
            bounds={},
            style={"color": style_colors[int(dataset.id[:2], 16) % len(style_colors)]},
            fields=dataset.fields,
            performance={
                "source_id": dataset.source_id,
                "dataset_id": dataset.id,
                "container": dataset.container,
                "relative_path": dataset.relative_path,
                "layer_name": dataset.layer_name,
                "fingerprint": dataset.fingerprint,
                "staging": True,
                "import_job_id": job_id,
            },
            data_path=dataset.relative_path,
            visible=False,
            locked=False,
            opacity=1.0,
        )
        self.session.add(layer)
        await self.session.commit()
        await self.session.refresh(layer)
        return layer

    async def get_layer(self, layer_id: int) -> Layer | None:
        return await self.session.get(Layer, layer_id)

    async def insert_batch(
        self,
        layer: Layer,
        job: Job,
        rows: list[dict[str, Any]],
        detail: JobProgressDetail,
        result_state: dict[str, Any],
    ) -> None:
        self.session.add_all([MapFeature(layer_id=layer.id, **row) for row in rows])
        layer.feature_count += len(rows)
        await self.update_job(
            job,
            status="running",
            progress=int((detail.imported_features / max(1, detail.total_features)) * 100),
            message=f"正在导入 {detail.current_layer}",
            detail=detail,
            extra_result=result_state,
            commit=False,
        )
        await self.session.commit()

    async def finalize_layer(self, layer: Layer, dataset: CatalogDataset) -> None:
        candidates = await self.imported_layers(dataset.source_id)
        for old_layer in candidates:
            metadata = old_layer.performance or {}
            if metadata.get("dataset_id") == dataset.id and old_layer.id != layer.id:
                await self.session.delete(old_layer)
        layer.visible = True
        layer.performance = {
            **dict(layer.performance or {}),
            "staging": False,
            "fingerprint": dataset.fingerprint,
        }
        await self.session.commit()

    async def delete_staging_features(self, layer_id: int) -> None:
        await self.session.execute(delete(MapFeature).where(MapFeature.layer_id == layer_id))
        await self.session.commit()

    async def mark_stale_jobs_interrupted(self) -> None:
        jobs = (
            await self.session.scalars(
                select(Job).where(
                    Job.job_type.in_(["import-sync", "import-data"]),
                    Job.status.in_(["queued", "running"]),
                )
            )
        ).all()
        for job in jobs:
            detail = JobProgressDetail.model_validate((job.result or {}).get("detail") or {})
            detail.stage = "interrupted"
            await self.update_job(
                job,
                status="interrupted",
                message="服务已重启，请手动继续任务。",
                detail=detail,
                commit=False,
            )
        await self.session.commit()
