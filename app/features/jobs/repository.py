from sqlalchemy.ext.asyncio import AsyncSession

from app.features.jobs.schemas import JobStatus


class JobRepository:
    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session

    async def get_status(self, job_id: str) -> JobStatus:
        return JobStatus(id=job_id)
