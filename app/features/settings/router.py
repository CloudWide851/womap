from fastapi import APIRouter, HTTPException, Response, status

from app.features.settings.schemas import (
    ImportOptionsUpdate,
    ImportSettingsResponse,
    ImportSourceCreate,
    ImportSourceResponse,
    ImportSourceTestRequest,
    ImportSourceTestResponse,
    ImportSourceUpdate,
    LocalRuntimeSettings,
    LocalRuntimeSettingsUpdate,
    RuntimeSettings,
)
from app.features.settings.credentials import CredentialStoreError
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


@router.get("/import-sources", response_model=ImportSettingsResponse)
async def get_import_sources() -> ImportSettingsResponse:
    return await SettingsService().get_import_settings()


@router.post(
    "/import-sources", response_model=ImportSourceResponse, status_code=status.HTTP_201_CREATED
)
async def create_import_source(payload: ImportSourceCreate) -> ImportSourceResponse:
    try:
        return await SettingsService().create_import_source(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CredentialStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.put("/import-sources/options", response_model=ImportSettingsResponse)
async def update_import_options(payload: ImportOptionsUpdate) -> ImportSettingsResponse:
    return await SettingsService().update_import_options(payload)


@router.put("/import-sources/{source_id}", response_model=ImportSourceResponse)
async def update_import_source(
    source_id: str, payload: ImportSourceUpdate
) -> ImportSourceResponse:
    try:
        return await SettingsService().update_import_source(source_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="数据源不存在。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CredentialStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete("/import-sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_import_source(source_id: str) -> Response:
    try:
        await SettingsService().delete_import_source(source_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="数据源不存在。") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/import-sources/{source_id}/test", response_model=ImportSourceTestResponse)
async def test_import_source(
    source_id: str, payload: ImportSourceTestRequest
) -> ImportSourceTestResponse:
    try:
        return await SettingsService().test_import_source(source_id, payload.password)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="数据源不存在。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CredentialStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
