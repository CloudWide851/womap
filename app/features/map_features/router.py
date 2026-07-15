from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.map_features.repository import MapFeatureRepository
from app.features.map_features.schemas import (
    FeatureCollectionResponse,
    MapFeatureCreate,
    MapFeatureCreateResponse,
    MapFeatureDeleteResponse,
    MapFeatureDetail,
    MapFeatureSummaryPage,
    MapFeatureUpdate,
)
from app.features.map_features.service import MapFeatureService
from app.features.workspaces.repository import WorkspaceRepository
from app.features.workspaces.service import WorkspaceService
from app.shared.database import get_session
from app.shared.errors import bad_request
from app.shared.pagination import BBoxQuery

router = APIRouter()


async def get_map_feature_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[MapFeatureService, None]:
    yield MapFeatureService(
        MapFeatureRepository(session),
        WorkspaceService(WorkspaceRepository(session)),
    )


@router.get("/layers/{layer_id}/features", response_model=FeatureCollectionResponse)
async def list_layer_features(
    layer_id: int,
    bbox: str = Query(..., description="min_x,min_y,max_x,max_y"),
    limit: int | None = Query(default=None, ge=1),
    cursor: str | None = None,
    simplify: float | None = Query(default=None, ge=0),
    workspace_id: int | None = Query(default=None, gt=0),
    service: MapFeatureService = Depends(get_map_feature_service),
) -> FeatureCollectionResponse:
    try:
        bbox_query = BBoxQuery.from_csv(bbox)
    except ValueError as exc:
        raise bad_request(str(exc)) from exc
    try:
        return await service.list_viewport_features(
            layer_id=layer_id,
            bbox=bbox_query,
            limit=limit,
            cursor=cursor,
            simplify=simplify,
            workspace_id=workspace_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="工作空间或图层引用不存在。") from exc
    except ValueError as exc:
        raise bad_request(str(exc)) from exc


@router.get(
    "/layers/{layer_id}/feature-summaries",
    response_model=MapFeatureSummaryPage,
)
async def list_layer_feature_summaries(
    layer_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    cursor: str | None = None,
    workspace_id: int | None = Query(default=None, gt=0),
    service: MapFeatureService = Depends(get_map_feature_service),
) -> MapFeatureSummaryPage:
    try:
        return await service.list_feature_summaries(layer_id, limit, cursor, workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="工作空间或图层引用不存在。") from exc
    except ValueError as exc:
        raise bad_request(str(exc)) from exc


@router.get(
    "/layers/{layer_id}/features/{feature_id}",
    response_model=MapFeatureDetail,
)
async def get_layer_feature(
    layer_id: int,
    feature_id: int,
    workspace_id: int | None = Query(default=None, gt=0),
    service: MapFeatureService = Depends(get_map_feature_service),
) -> MapFeatureDetail:
    try:
        return await service.get_feature_detail(layer_id, feature_id, workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="图斑不存在或不属于当前工作空间。") from exc


@router.post(
    "/layers/{layer_id}/features",
    response_model=MapFeatureCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_layer_feature(
    layer_id: int,
    payload: MapFeatureCreate,
    service: MapFeatureService = Depends(get_map_feature_service),
) -> MapFeatureCreateResponse:
    try:
        return await service.create_polygon_feature(layer_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="目标图层不存在。") from exc
    except ValueError as exc:
        raise bad_request(str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put(
    "/layers/{layer_id}/features/{feature_id}",
    response_model=MapFeatureCreateResponse,
)
async def update_layer_feature(
    layer_id: int,
    feature_id: int,
    payload: MapFeatureUpdate,
    service: MapFeatureService = Depends(get_map_feature_service),
) -> MapFeatureCreateResponse:
    try:
        return await service.update_polygon_feature(layer_id, feature_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="目标图层或图斑不存在。") from exc
    except ValueError as exc:
        raise bad_request(str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete(
    "/layers/{layer_id}/features/{feature_id}",
    response_model=MapFeatureDeleteResponse,
)
async def delete_layer_feature(
    layer_id: int,
    feature_id: int,
    revision: int = Query(..., ge=1),
    service: MapFeatureService = Depends(get_map_feature_service),
) -> MapFeatureDeleteResponse:
    try:
        return await service.delete_polygon_feature(layer_id, feature_id, revision)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="目标图层或图斑不存在。") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
