from collections.abc import AsyncGenerator

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.workspaces.repository import WorkspaceRepository
from app.features.workspaces.package_io import WorkspacePackageError
from app.features.workspaces.package_repository import WorkspacePackageRepository
from app.features.workspaces.package_service import (
    WorkspacePackageConflictError,
    WorkspacePackageService,
)
from app.features.workspaces.schemas import (
    WorkspaceCatalogResponse,
    WorkspaceCreate,
    WorkspaceDetail,
    WorkspacePackageExportRequest,
    WorkspacePackageImportRequest,
    WorkspacePackagePreview,
    WorkspaceSummary,
    WorkspaceUpdate,
)
from app.features.workspaces.service import WorkspaceConflictError, WorkspaceService
from app.shared.database import get_session


router = APIRouter()


async def get_workspace_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[WorkspaceService, None]:
    yield WorkspaceService(WorkspaceRepository(session))


async def get_workspace_package_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[WorkspacePackageService, None]:
    yield WorkspacePackageService(
        WorkspacePackageRepository(session),
        WorkspaceService(WorkspaceRepository(session)),
    )


@router.get("", response_model=list[WorkspaceSummary])
async def list_workspaces(
    service: WorkspaceService = Depends(get_workspace_service),
) -> list[WorkspaceSummary]:
    return await service.list_workspaces()


@router.post("", response_model=WorkspaceDetail, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceCreate,
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceDetail:
    try:
        return await service.create_workspace(payload)
    except WorkspaceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/catalog", response_model=WorkspaceCatalogResponse)
async def get_workspace_catalog(
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceCatalogResponse:
    return await service.catalog()


@router.post(
    "/{workspace_id}/exports",
    status_code=status.HTTP_202_ACCEPTED,
)
async def export_workspace_package(
    workspace_id: int,
    payload: WorkspacePackageExportRequest | None = Body(default=None),
    service: WorkspacePackageService = Depends(get_workspace_package_service),
):
    try:
        job = await service.queue_export(
            workspace_id,
            include_rasters=bool(payload and payload.include_rasters),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="工作空间不存在。") from exc
    return job


@router.get("/packages/exports/{job_id}/download")
async def download_workspace_package(
    job_id: str,
    service: WorkspacePackageService = Depends(get_workspace_package_service),
) -> FileResponse:
    try:
        path, filename = await service.download_path(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="工作空间包尚未生成或已不存在。") from exc
    except WorkspacePackageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(path=path, filename=filename, media_type="application/zip")


@router.post("/packages/preview", response_model=WorkspacePackagePreview)
async def preview_workspace_package(
    package: UploadFile = File(...),
    service: WorkspacePackageService = Depends(get_workspace_package_service),
) -> WorkspacePackagePreview:
    try:
        return await service.save_and_preview(package)
    except WorkspacePackageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await package.close()


@router.post("/packages/imports", status_code=status.HTTP_202_ACCEPTED)
async def import_workspace_package(
    payload: WorkspacePackageImportRequest,
    service: WorkspacePackageService = Depends(get_workspace_package_service),
):
    try:
        job = await service.queue_import(payload)
    except WorkspacePackageConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WorkspacePackageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return job


@router.get("/{workspace_id}", response_model=WorkspaceDetail)
async def get_workspace(
    workspace_id: int,
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceDetail:
    try:
        return await service.get_workspace(workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="工作空间不存在。") from exc


@router.put("/{workspace_id}", response_model=WorkspaceDetail)
async def update_workspace(
    workspace_id: int,
    payload: WorkspaceUpdate,
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceDetail:
    try:
        return await service.update_workspace(workspace_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="工作空间不存在。") from exc
    except WorkspaceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: int,
    service: WorkspaceService = Depends(get_workspace_service),
) -> Response:
    try:
        await service.delete_workspace(workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="工作空间不存在。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
