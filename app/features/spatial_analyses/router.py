from collections.abc import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.jobs.schemas import JobStatus
from app.features.map_features.repository import MapFeatureRepository
from app.features.map_features.service import MapFeatureService
from app.features.spatial_analyses.repository import SpatialAnalysisRepository
from app.features.spatial_analyses.schemas import (
    SpatialAnalysisCreate,
    SpatialAnalysisHitPage,
    SpatialAnalysisResult,
)
from app.features.spatial_analyses.service import (
    SpatialAnalysisService,
    execute_spatial_analysis_export_job,
    execute_spatial_analysis_job,
)
from app.features.workspaces.repository import WorkspaceRepository
from app.features.workspaces.service import WorkspaceService
from app.shared.database import get_session

router = APIRouter()


async def get_spatial_analysis_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[SpatialAnalysisService, None]:
    workspace_service = WorkspaceService(WorkspaceRepository(session))
    yield SpatialAnalysisService(
        SpatialAnalysisRepository(session),
        workspace_service,
        MapFeatureService(MapFeatureRepository(session), workspace_service),
    )


@router.post("", response_model=JobStatus, status_code=status.HTTP_202_ACCEPTED)
async def create_spatial_analysis(
    payload: SpatialAnalysisCreate,
    background_tasks: BackgroundTasks,
    service: SpatialAnalysisService = Depends(get_spatial_analysis_service),
) -> JobStatus:
    try:
        job = await service.queue(payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="工作空间、图层或目标图斑不存在。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(execute_spatial_analysis_job, job.id)
    return job


@router.get("/{job_id}", response_model=SpatialAnalysisResult)
async def get_spatial_analysis(
    job_id: str,
    service: SpatialAnalysisService = Depends(get_spatial_analysis_service),
) -> SpatialAnalysisResult:
    try:
        return await service.get_result(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="空间分析任务不存在。") from exc


@router.get("/{job_id}/hits", response_model=SpatialAnalysisHitPage)
async def list_spatial_analysis_hits(
    job_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    cursor: str | None = None,
    include_geometry: bool = Query(default=False),
    service: SpatialAnalysisService = Depends(get_spatial_analysis_service),
) -> SpatialAnalysisHitPage:
    try:
        return await service.hits(
            job_id,
            limit=limit,
            cursor=cursor,
            include_geometry=include_geometry,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="空间分析任务不存在。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{job_id}/cancel", response_model=JobStatus)
async def cancel_spatial_analysis(
    job_id: str,
    service: SpatialAnalysisService = Depends(get_spatial_analysis_service),
) -> JobStatus:
    try:
        return await service.cancel(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="空间分析任务不存在。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/{job_id}/exports",
    response_model=JobStatus,
    status_code=status.HTTP_202_ACCEPTED,
)
async def export_spatial_analysis(
    job_id: str,
    background_tasks: BackgroundTasks,
    service: SpatialAnalysisService = Depends(get_spatial_analysis_service),
) -> JobStatus:
    try:
        job = await service.queue_export(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="空间分析任务不存在。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(execute_spatial_analysis_export_job, job.id)
    return job


@router.get("/exports/{export_job_id}/download")
async def download_spatial_analysis_export(
    export_job_id: str,
    service: SpatialAnalysisService = Depends(get_spatial_analysis_service),
) -> FileResponse:
    try:
        path, filename = await service.download_path(export_job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="分析结果导出尚未完成或已不存在。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(path=path, filename=filename, media_type="application/zip")
