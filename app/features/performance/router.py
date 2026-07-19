from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.performance.schemas import (
    PerformanceCapabilityResponse,
    PerformanceMetricsResponse,
)
from app.features.performance.service import PerformanceService
from app.shared.database import get_session


router = APIRouter()


async def get_performance_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[PerformanceService, None]:
    yield PerformanceService(session)


@router.get("/capabilities", response_model=PerformanceCapabilityResponse)
async def get_performance_capabilities(
    service: PerformanceService = Depends(get_performance_service),
) -> PerformanceCapabilityResponse:
    return await service.get_capabilities()


@router.get("/metrics", response_model=PerformanceMetricsResponse)
async def get_performance_metrics(
    service: PerformanceService = Depends(get_performance_service),
) -> PerformanceMetricsResponse:
    return await service.get_metrics()
