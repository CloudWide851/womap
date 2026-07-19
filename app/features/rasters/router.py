from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.jobs.schemas import JobStatus
from app.features.layers.schemas import LayerSummary
from app.features.rasters.repository import RasterRepository
from app.features.rasters.schemas import (
    RasterCleanupResponse,
    RasterDeriveRequest,
    RasterExportRequest,
    RasterHistogramResponse,
    RasterPixelResponse,
    RasterStorageStatus,
    RasterStyle,
)
from app.features.rasters.service import RasterService
from app.features.rasters.storage import RasterStorageError
from app.shared.database import get_session
from app.shared.runtime_metrics import runtime_metrics

router = APIRouter()


async def get_raster_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[RasterService, None]:
    yield RasterService(RasterRepository(session))


def _parse_range(value: str | None, size: int) -> tuple[int, int] | None:
    if not value:
        return None
    if not value.startswith("bytes=") or "," in value:
        raise ValueError("只支持单段 bytes Range。")
    spec = value.removeprefix("bytes=").strip()
    if "-" not in spec:
        raise ValueError("Range 格式无效。")
    start_text, end_text = spec.split("-", 1)
    if not start_text:
        suffix = int(end_text)
        if suffix <= 0:
            raise ValueError("Range 后缀长度无效。")
        return max(0, size - suffix), size - 1
    start = int(start_text)
    end = int(end_text) if end_text else size - 1
    if start < 0 or start >= size or end < start:
        raise ValueError("Range 超出文件范围。")
    return start, min(end, size - 1)


def _file_chunks(path: Path, start: int, length: int) -> Iterator[bytes]:
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining:
            chunk = handle.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@router.get("/{layer_id}/asset")
async def raster_asset(
    layer_id: int,
    request: Request,
    range_header: str | None = Header(default=None, alias="Range"),
    service: RasterService = Depends(get_raster_service),
) -> Response:
    try:
        path, etag, last_modified = await service.asset(layer_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="栅格资产不存在。") from exc
    except (ValueError, RasterStorageError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    headers = {
        "Accept-Ranges": "bytes",
        "ETag": etag,
        "Last-Modified": last_modified,
        "Cache-Control": "private, max-age=31536000, immutable",
    }
    if request.headers.get("if-none-match") == etag:
        runtime_metrics.range_response(status.HTTP_304_NOT_MODIFIED, 0)
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    size = path.stat().st_size
    try:
        selected = _parse_range(range_header, size)
    except (TypeError, ValueError) as exc:
        headers["Content-Range"] = f"bytes */{size}"
        runtime_metrics.range_response(status.HTTP_416_RANGE_NOT_SATISFIABLE, 0)
        raise HTTPException(status_code=416, detail=str(exc), headers=headers) from exc
    if selected is None:
        headers["Content-Length"] = str(size)
        runtime_metrics.range_response(status.HTTP_200_OK, size)
        return StreamingResponse(
            _file_chunks(path, 0, size), media_type="image/tiff", headers=headers
        )
    start_byte, end_byte = selected
    length = end_byte - start_byte + 1
    headers.update(
        {
            "Content-Range": f"bytes {start_byte}-{end_byte}/{size}",
            "Content-Length": str(length),
        }
    )
    runtime_metrics.range_response(status.HTTP_206_PARTIAL_CONTENT, length)
    return StreamingResponse(
        _file_chunks(path, start_byte, length),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type="image/tiff",
        headers=headers,
    )


@router.get("/{layer_id}/histogram", response_model=RasterHistogramResponse)
async def raster_histogram(
    layer_id: int,
    band: int = Query(default=1, ge=1, le=256),
    bins: int = Query(default=256, ge=16, le=512),
    service: RasterService = Depends(get_raster_service),
) -> RasterHistogramResponse:
    try:
        return await service.histogram(layer_id, band, bins)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="栅格图层不存在。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{layer_id}/pixel", response_model=RasterPixelResponse)
async def raster_pixel(
    layer_id: int,
    x: float,
    y: float,
    crs: str = Query(default="EPSG:3857", pattern=r"^EPSG:\d+$"),
    service: RasterService = Depends(get_raster_service),
) -> RasterPixelResponse:
    try:
        return await service.pixel(layer_id, x, y, crs)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="栅格图层不存在。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{layer_id}/style", response_model=LayerSummary)
async def update_raster_style(
    layer_id: int,
    style_payload: RasterStyle,
    service: RasterService = Depends(get_raster_service),
) -> LayerSummary:
    try:
        return await service.update_style(layer_id, style_payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="栅格图层不存在。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{layer_id}/derive", response_model=JobStatus, status_code=202)
async def derive_raster(
    layer_id: int,
    payload: RasterDeriveRequest,
    service: RasterService = Depends(get_raster_service),
) -> JobStatus:
    try:
        job = await service.queue_derive(layer_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="栅格图层不存在。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return job


@router.post("/exports", response_model=JobStatus, status_code=202)
async def export_rasters(
    payload: RasterExportRequest,
    service: RasterService = Depends(get_raster_service),
) -> JobStatus:
    try:
        job = await service.queue_export(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return job


@router.get("/exports/{job_id}/download")
async def download_raster_export(
    job_id: str,
    service: RasterService = Depends(get_raster_service),
) -> FileResponse:
    try:
        path, filename = await service.export_path(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="栅格导出尚未完成或已不存在。") from exc
    return FileResponse(path, filename=filename, media_type="application/zip")


@router.get("/storage/status", response_model=RasterStorageStatus)
async def raster_storage_status(
    service: RasterService = Depends(get_raster_service),
) -> RasterStorageStatus:
    return await service.storage_status()


@router.post("/storage/cleanup", response_model=RasterCleanupResponse)
async def cleanup_raster_storage(
    service: RasterService = Depends(get_raster_service),
) -> RasterCleanupResponse:
    return await service.cleanup()
