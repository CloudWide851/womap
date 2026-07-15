from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from sqlalchemy import false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.jobs.repository import JobRepository
from app.features.jobs.schemas import JobStatus, WorkspacePackageJobProgressDetail
from app.features.workspaces.schemas import WorkspaceFeatureSelection
from app.models.job import Job
from app.models.map_feature import MapFeature
from app.models.project import Project


class WorkspacePackageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_job(
        self,
        *,
        job_type: str,
        workspace_id: int | None,
        operation: str,
        payload: dict[str, Any] | None = None,
    ) -> JobStatus:
        detail = WorkspacePackageJobProgressDetail(
            operation=operation,
            workspace_id=workspace_id,
        )
        job = Job(
            id=f"{job_type}-{uuid4().hex}",
            job_type=job_type,
            status="queued",
            progress=0,
            message="工作空间任务已进入队列。",
            payload={"workspace_id": workspace_id, **(payload or {})},
            result={"detail": detail.model_dump()},
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
        detail: WorkspacePackageJobProgressDetail | None = None,
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
            result["detail"] = detail.model_dump()
        if extra_result:
            result.update(extra_result)
        job.result = result
        await self.session.commit()

    async def list_feature_rows(
        self,
        layer_id: int,
        selection: WorkspaceFeatureSelection,
    ) -> list[dict[str, Any]]:
        statement = (
            select(
                MapFeature.id,
                MapFeature.source_feature_id,
                MapFeature.properties,
                func.ST_AsGeoJSON(MapFeature.geom).label("geometry_json"),
            )
            .where(MapFeature.layer_id == layer_id)
            .order_by(MapFeature.id)
        )
        if selection.mode == "include":
            filters = []
            if selection.feature_ids:
                filters.append(MapFeature.id.in_(selection.feature_ids))
            if selection.source_feature_ids:
                filters.append(MapFeature.source_feature_id.in_(selection.source_feature_ids))
            statement = statement.where(or_(*filters) if filters else false())
        rows = (await self.session.execute(statement)).mappings().all()
        result: list[dict[str, Any]] = []
        for row in rows:
            raw_geometry = row["geometry_json"]
            geometry = json.loads(raw_geometry) if isinstance(raw_geometry, str) else raw_geometry
            if not isinstance(geometry, dict):
                continue
            result.append(
                {
                    "id": int(row["id"]),
                    "source_feature_id": row["source_feature_id"],
                    "properties": dict(row["properties"] or {}),
                    "geometry": geometry,
                }
            )
        return result

    async def find_workspace_by_uuid(self, workspace_uuid: str) -> Project | None:
        projects = (await self.session.scalars(select(Project))).all()
        for project in projects:
            if str((project.current_view or {}).get("workspace_uuid") or "") == workspace_uuid:
                return project
        return None

    async def rollback(self) -> None:
        await self.session.rollback()

    async def mark_stale_jobs_interrupted(self) -> None:
        jobs = (
            await self.session.scalars(
                select(Job).where(
                    Job.job_type.in_(["workspace-export", "workspace-import"]),
                    Job.status.in_(["queued", "running"]),
                )
            )
        ).all()
        for job in jobs:
            detail = WorkspacePackageJobProgressDetail.model_validate(
                (job.result or {}).get("detail") or {}
            )
            detail.stage = "interrupted"
            job.status = "interrupted"
            job.message = "服务已重启，工作空间包任务已中断。"
            job.result = {**dict(job.result or {}), "detail": detail.model_dump()}
        await self.session.commit()
