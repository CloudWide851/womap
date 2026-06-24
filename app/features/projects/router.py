from fastapi import APIRouter

from app.features.projects.schemas import ProjectSummary
from app.features.projects.service import ProjectService

router = APIRouter()


@router.get("", response_model=list[ProjectSummary])
async def list_projects() -> list[ProjectSummary]:
    return await ProjectService().list_projects()
