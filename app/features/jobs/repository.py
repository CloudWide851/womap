from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.jobs.schemas import JobProgressDetail, JobStatus
from app.models.job import Job


class JobRepository:
    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session

    async def get_status(self, job_id: str) -> JobStatus:
        if self.session is None:
            return JobStatus(id=job_id)
        job = await self.session.get(Job, job_id)
        return self.to_status(job) if job else JobStatus(id=job_id)

    async def list_statuses(self, limit: int = 30) -> list[JobStatus]:
        if self.session is None:
            return []
        jobs = (
            await self.session.scalars(
                select(Job).order_by(Job.updated_at.desc()).limit(max(1, min(limit, 100)))
            )
        ).all()
        return [self.to_status(job) for job in jobs]

    @staticmethod
    def to_status(job: Job) -> JobStatus:
        result = dict(job.result or {})
        detail = result.get("detail") if isinstance(result.get("detail"), dict) else {}
        return JobStatus(
            id=job.id,
            job_type=job.job_type,
            status=job.status,
            progress=job.progress,
            message=job.message,
            detail=JobProgressDetail.model_validate(detail),
            result=result,
        )
