from fastapi import APIRouter

from app.schemas.layer import LayerSummary

router = APIRouter()


@router.get("", response_model=list[LayerSummary])
async def list_layers() -> list[LayerSummary]:
    return []
