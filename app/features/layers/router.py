from fastapi import APIRouter

from app.features.layers.schemas import LayerSummary
from app.features.layers.service import LayerService

router = APIRouter()


@router.get("", response_model=list[LayerSummary])
async def list_layers() -> list[LayerSummary]:
    return await LayerService().list_layers()
