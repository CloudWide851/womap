from __future__ import annotations

import shutil
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.features.exports.repository import ExportRepository
from app.features.exports.schemas import ExportRequest
from app.features.exports.service import (
    ExportDependencyError,
    ExportNoDataError,
    ExportRequestError,
    ExportService,
)
from app.shared.database import get_session

router = APIRouter()


async def get_export_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[ExportService, None]:
    yield ExportService(repository=ExportRepository(session=session))


@router.post("")
async def export_layers(
    payload: ExportRequest,
    service: ExportService = Depends(get_export_service),
) -> FileResponse:
    try:
        archive = await service.export_layers(payload.format, payload.layer_ids)
    except ExportRequestError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ExportNoDataError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ExportDependencyError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc

    return FileResponse(
        path=archive.path,
        filename=archive.filename,
        media_type=archive.media_type,
        background=BackgroundTask(shutil.rmtree, archive.cleanup_path, ignore_errors=True),
    )
