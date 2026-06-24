from fastapi import APIRouter

from app.features.settings.schemas import RuntimeSettings
from app.features.settings.service import SettingsService

router = APIRouter()


@router.get("/runtime", response_model=RuntimeSettings)
async def get_runtime_settings() -> RuntimeSettings:
    return await SettingsService().get_runtime_settings()
