from fastapi import APIRouter

from app.features.basemaps.schemas import BasemapProvider
from app.features.basemaps.service import BasemapService

router = APIRouter()


@router.get("", response_model=list[BasemapProvider])
async def list_basemaps() -> list[BasemapProvider]:
    return await BasemapService().list_basemaps()
