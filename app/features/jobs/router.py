from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.jobs.repository import JobRepository
from app.features.jobs.schemas import JobStatus
from app.features.jobs.service import JobService
from app.shared.database import get_session

router = APIRouter()


async def get_job_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[JobService, None]:
    yield JobService(JobRepository(session))


@router.get("", response_model=list[JobStatus])
async def list_jobs(
    limit: int = Query(default=30, ge=1, le=100),
    service: JobService = Depends(get_job_service),
) -> list[JobStatus]:
    return await service.list_statuses(limit)


@router.get("/{job_id}", response_model=JobStatus)
async def get_job_status(
    job_id: str, service: JobService = Depends(get_job_service)
) -> JobStatus:
    return await service.get_status(job_id)
