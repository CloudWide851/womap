from shapely.errors import GEOSException
from shapely.geometry import Polygon, shape

from app.features.map_features.repository import MapFeatureRepository
from app.features.map_features.schemas import (
    FeatureCollectionResponse,
    MapFeatureCreate,
    MapFeatureCreateResponse,
)
from app.shared.config import get_settings
from app.shared.pagination import BBoxQuery, FeatureQueryMeta


class MapFeatureService:
    def __init__(self, repository: MapFeatureRepository | None = None) -> None:
        self.repository = repository or MapFeatureRepository()
        self.settings = get_settings()

    async def list_viewport_features(
        self,
        layer_id: int,
        bbox: BBoxQuery,
        limit: int | None,
        cursor: str | None,
        simplify: float | None,
    ) -> FeatureCollectionResponse:
        effective_limit = self.settings.performance.clamp_feature_limit(limit)
        effective_simplify = simplify
        if effective_simplify is None:
            effective_simplify = self.settings.performance.simplify_tolerance
        truncated = limit is not None and limit > effective_limit
        warning = None
        if truncated:
            warning = "请求数量超过系统上限，已按最大安全窗口返回。"

        features, next_cursor, has_more = await self.repository.list_viewport_features(
            layer_id=layer_id,
            bbox=bbox,
            limit=effective_limit,
            cursor=cursor,
            simplify=effective_simplify,
        )
        if has_more:
            truncated = True
            warning = "当前视口要素超过安全上限，请放大地图查看完整数据。"
        return FeatureCollectionResponse(
            features=features,
            meta=FeatureQueryMeta(
                limit=effective_limit,
                returned=len(features),
                next_cursor=next_cursor,
                truncated=truncated,
                warning=warning,
                bbox=bbox.as_tuple(),
                simplify=effective_simplify,
                cache_hit=False,
                strategy="postgis-bbox-gist",
            ),
        )

    async def create_polygon_feature(
        self,
        layer_id: int,
        payload: MapFeatureCreate,
    ) -> MapFeatureCreateResponse:
        layer = await self.repository.get_layer(layer_id)
        if layer is None:
            raise KeyError(layer_id)
        if layer.locked:
            raise RuntimeError("目标图层已锁定，无法新增图斑。")
        if not layer.visible:
            raise RuntimeError("目标图层已隐藏，无法新增图斑。")
        if layer.geometry_type not in {"Polygon", "Mixed"}:
            raise RuntimeError("目标图层的几何类型不支持 Polygon 图斑。")
        polygon = self._validate_polygon(payload)
        feature, layer_summary = await self.repository.create_polygon_feature(
            layer,
            polygon,
            payload.properties,
        )
        return MapFeatureCreateResponse(feature=feature, layer=layer_summary)

    @staticmethod
    def _validate_polygon(payload: MapFeatureCreate) -> Polygon:
        coordinates = payload.geometry.coordinates
        if not coordinates or not coordinates[0]:
            raise ValueError("Polygon 坐标不能为空。")
        outer_ring = coordinates[0]
        distinct_vertices = {tuple(point[:2]) for point in outer_ring}
        if len(distinct_vertices) < 3:
            raise ValueError("Polygon 至少需要三个不同顶点。")
        try:
            geometry = shape(payload.geometry.model_dump())
        except (GEOSException, TypeError, ValueError) as exc:
            raise ValueError("Polygon 坐标格式无效。") from exc
        if not isinstance(geometry, Polygon):
            raise ValueError("仅支持 Polygon 几何。")
        if not geometry.is_valid:
            raise ValueError("Polygon 存在自相交或其他拓扑错误。")
        if geometry.is_empty or geometry.area <= 0:
            raise ValueError("Polygon 不能为空或面积为零。")
        return geometry
