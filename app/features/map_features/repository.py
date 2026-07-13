import json
from typing import Any

from geoalchemy2.shape import from_shape
from shapely.geometry import Polygon, mapping
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.layers.repository import LayerRepository
from app.features.layers.schemas import LayerSummary
from app.features.map_features.schemas import FeatureGeometry, MapFeatureItem
from app.models.layer import Layer
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

    async def get_layer(self, layer_id: int) -> Layer | None:
        if self.session is None:
            return None
        return await self.session.get(Layer, layer_id)

    async def create_polygon_feature(
        self,
        layer: Layer,
        polygon: Polygon,
        properties: dict[str, Any],
    ) -> tuple[MapFeatureItem, LayerSummary]:
        if self.session is None:
            raise RuntimeError("数据库会话不可用。")
        min_x, min_y, max_x, max_y = polygon.bounds
        bbox = {
            "min_x": float(min_x),
            "min_y": float(min_y),
            "max_x": float(max_x),
            "max_y": float(max_y),
        }
        feature = MapFeature(
            layer_id=layer.id,
            source_feature_id=None,
            geom=from_shape(polygon, srid=3857),
            properties=properties,
            bbox=bbox,
            area=float(polygon.area),
            perimeter=float(polygon.length),
            revision=1,
        )
        previous_feature_count = layer.feature_count
        previous_bounds = dict(layer.bounds or {})
        self.session.add(feature)
        layer.feature_count += 1
        layer.bounds = self._merge_bounds(layer.bounds, bbox)
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            layer.feature_count = previous_feature_count
            layer.bounds = previous_bounds
            raise
        await self.session.refresh(feature)
        await self.session.refresh(layer)
        return (
            MapFeatureItem(
                id=feature.id,
                geometry=FeatureGeometry.model_validate(mapping(polygon)),
                properties=dict(feature.properties or {}),
            ),
            LayerRepository.to_summary(layer),
        )

    @staticmethod
    def _merge_bounds(current: dict | None, added: dict[str, float]) -> dict[str, float]:
        if not current or not all(
            key in current for key in ("min_x", "min_y", "max_x", "max_y")
        ):
            return dict(added)
        return {
            "min_x": min(float(current["min_x"]), added["min_x"]),
            "min_y": min(float(current["min_y"]), added["min_y"]),
            "max_x": max(float(current["max_x"]), added["max_x"]),
            "max_y": max(float(current["max_y"]), added["max_y"]),
        }
