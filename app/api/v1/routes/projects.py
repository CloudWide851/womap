from fastapi import APIRouter

from app.schemas.project import ProjectSummary

router = APIRouter()


@router.get("", response_model=list[ProjectSummary])
async def list_projects() -> list[ProjectSummary]:
    return []
