from app.features.map_features.repository import MapFeatureRepository
from app.features.map_features.schemas import FeatureCollectionResponse
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

        features = await self.repository.list_viewport_features(
            layer_id=layer_id,
            bbox=bbox,
            limit=effective_limit,
            cursor=cursor,
            simplify=effective_simplify,
        )
        return FeatureCollectionResponse(
            features=features,
            meta=FeatureQueryMeta(
                limit=effective_limit,
                returned=len(features),
                truncated=truncated,
                warning=warning,
                bbox=bbox.as_tuple(),
                simplify=effective_simplify,
                cache_hit=False,
                strategy="postgis-bbox-gist",
            ),
        )
