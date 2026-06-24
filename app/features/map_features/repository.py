from sqlalchemy.ext.asyncio import AsyncSession

from app.features.map_features.schemas import MapFeatureItem
from app.shared.pagination import BBoxQuery


class MapFeatureRepository:
    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session

    async def list_viewport_features(
        self,
        layer_id: int,
        bbox: BBoxQuery,
        limit: int,
        cursor: str | None,
        simplify: float | None,
    ) -> list[MapFeatureItem]:
        _ = (layer_id, bbox, limit, cursor, simplify)
        return []
