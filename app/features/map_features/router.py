from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.map_features.repository import MapFeatureRepository
from app.features.map_features.schemas import (
    FeatureCollectionResponse,
    MapFeatureCreate,
    MapFeatureCreateResponse,
)
from app.features.map_features.service import MapFeatureService
from app.shared.database import get_session
from app.shared.errors import bad_request
from app.shared.pagination import BBoxQuery

router = APIRouter()


async def get_map_feature_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[MapFeatureService, None]:
    yield MapFeatureService(MapFeatureRepository(session))


@router.get("/layers/{layer_id}/features", response_model=FeatureCollectionResponse)
async def list_layer_features(
    layer_id: int,
    bbox: str = Query(..., description="min_x,min_y,max_x,max_y"),
    limit: int | None = Query(default=None, ge=1),
    cursor: str | None = None,
    simplify: float | None = Query(default=None, ge=0),
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
        )
    except ValueError as exc:
        raise bad_request(str(exc)) from exc


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
