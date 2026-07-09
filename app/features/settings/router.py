from fastapi import APIRouter

from app.features.settings.schemas import (
    LocalRuntimeSettings,
    LocalRuntimeSettingsUpdate,
    RuntimeSettings,
)
from app.features.settings.service import SettingsService

router = APIRouter()


@router.get("/runtime", response_model=RuntimeSettings)
async def get_runtime_settings() -> RuntimeSettings:
    return await SettingsService().get_runtime_settings()


@router.get("/local", response_model=LocalRuntimeSettings)
async def get_local_runtime_settings() -> LocalRuntimeSettings:
    return await SettingsService().get_local_runtime_settings()


@router.put("/local", response_model=LocalRuntimeSettings)
async def update_local_runtime_settings(
    payload: LocalRuntimeSettingsUpdate,
) -> LocalRuntimeSettings:
    return await SettingsService().update_local_runtime_settings(payload)
