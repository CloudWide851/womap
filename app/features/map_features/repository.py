import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.map_features.schemas import FeatureGeometry, MapFeatureItem
from app.models.map_feature import MapFeature
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
    ) -> tuple[list[MapFeatureItem], str | None, bool]:
        if self.session is None:
            return [], None, False
        cursor_id = 0
        if cursor:
            try:
                cursor_id = int(cursor)
            except ValueError as exc:
                raise ValueError("cursor 必须是有效的要素 ID。") from exc

        envelope = func.ST_MakeEnvelope(*bbox.as_tuple(), 3857)
        geometry_expression = MapFeature.geom
        if simplify and simplify > 0:
            geometry_expression = func.ST_SimplifyPreserveTopology(MapFeature.geom, simplify)
        statement = (
            select(
                MapFeature.id,
                MapFeature.properties,
                func.ST_AsGeoJSON(geometry_expression).label("geometry_json"),
            )
            .where(
                MapFeature.layer_id == layer_id,
                MapFeature.id > cursor_id,
                func.ST_Intersects(MapFeature.geom, envelope),
            )
            .order_by(MapFeature.id)
            .limit(limit + 1)
        )
        rows = (await self.session.execute(statement)).mappings().all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        features: list[MapFeatureItem] = []
        for row in rows:
            raw_geometry = row["geometry_json"]
            geometry = json.loads(raw_geometry) if isinstance(raw_geometry, str) else raw_geometry
            features.append(
                MapFeatureItem(
                    id=int(row["id"]),
                    geometry=FeatureGeometry.model_validate(geometry) if geometry else None,
                    properties=dict(row["properties"] or {}),
                )
            )
        next_cursor = str(rows[-1]["id"]) if has_more and rows else None
        return features, next_cursor, has_more
