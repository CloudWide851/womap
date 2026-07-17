from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.exports.repository import ExportRepository
from app.features.exports.schemas import ExportRequest
from app.features.exports.service import (
    ExportDependencyError,
    ExportNoDataError,
    ExportRequestError,
    ExportService,
)
from app.shared.database import get_session
from app.features.jobs.schemas import JobStatus

router = APIRouter()


async def get_export_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[ExportService, None]:
    yield ExportService(repository=ExportRepository(session=session))


@router.post("", response_model=JobStatus, status_code=status.HTTP_202_ACCEPTED)
async def export_layers(
    payload: ExportRequest,
    service: ExportService = Depends(get_export_service),
) -> JobStatus:
    try:
        return await service.queue_export(payload.format, payload.layer_ids)
    except ExportRequestError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ExportNoDataError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ExportDependencyError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc


@router.get("/{job_id}/download")
async def download_export(
    job_id: str,
    service: ExportService = Depends(get_export_service),
) -> FileResponse:
    try:
        path, filename = await service.download_path(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="矢量成果尚未完成或已不存在。") from exc
    return FileResponse(path, filename=filename, media_type="application/zip")
