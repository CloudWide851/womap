from app.features.jobs.repository import JobRepository
from app.features.jobs.schemas import JobStatus


class JobService:
    def __init__(self, repository: JobRepository | None = None) -> None:
        self.repository = repository or JobRepository()

    async def get_status(self, job_id: str) -> JobStatus:
        return await self.repository.get_status(job_id)

    async def list_statuses(self, limit: int = 30) -> list[JobStatus]:
        return await self.repository.list_statuses(limit)
