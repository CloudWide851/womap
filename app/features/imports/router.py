from collections.abc import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.imports.repository import ImportRepository
from app.features.imports.schemas import ImportCatalog, ImportRequest, SyncRequest
from app.features.imports.service import ImportService, execute_import_job
from app.features.jobs.schemas import JobStatus
from app.shared.database import get_session

router = APIRouter()


async def get_import_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[ImportService, None]:
    yield ImportService(ImportRepository(session))


@router.post("/sync", response_model=JobStatus, status_code=status.HTTP_202_ACCEPTED)
async def sync_import_source(
    payload: SyncRequest,
    background_tasks: BackgroundTasks,
    service: ImportService = Depends(get_import_service),
) -> JobStatus:
    try:
        job = await service.queue_sync(payload.source_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="数据源不存在或未启用。") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(execute_import_job, job.id)
    return job


@router.get("/catalog", response_model=ImportCatalog)
async def get_import_catalog(
    source_id: str, service: ImportService = Depends(get_import_service)
) -> ImportCatalog:
    try:
        return await service.get_catalog(source_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="数据源不存在或未启用。") from exc


@router.post("", response_model=JobStatus, status_code=status.HTTP_202_ACCEPTED)
async def import_datasets(
    payload: ImportRequest,
    background_tasks: BackgroundTasks,
    service: ImportService = Depends(get_import_service),
) -> JobStatus:
    try:
        job = await service.queue_import(payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="数据源不存在或未启用。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(execute_import_job, job.id)
    return job


@router.post("/{job_id}/resume", response_model=JobStatus, status_code=status.HTTP_202_ACCEPTED)
async def resume_import_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    service: ImportService = Depends(get_import_service),
) -> JobStatus:
    try:
        job = await service.resume(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="导入任务不存在。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(execute_import_job, job.id)
    return job
