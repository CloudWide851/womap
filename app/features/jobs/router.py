from fastapi import APIRouter

from app.features.jobs.schemas import JobStatus
from app.features.jobs.service import JobService

router = APIRouter()


@router.get("/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str) -> JobStatus:
    return await JobService().get_status(job_id)
