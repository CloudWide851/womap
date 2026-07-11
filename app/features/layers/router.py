from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.layers.repository import LayerRepository
from app.features.layers.schemas import LayerSummary
from app.features.layers.service import LayerService
from app.shared.database import get_session

router = APIRouter()


async def get_layer_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[LayerService, None]:
    yield LayerService(LayerRepository(session))


@router.get("", response_model=list[LayerSummary])
async def list_layers(service: LayerService = Depends(get_layer_service)) -> list[LayerSummary]:
    return await service.list_layers()
