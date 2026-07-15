import json
from typing import Any

from geoalchemy2.shape import from_shape
from shapely.geometry import Polygon, mapping
from sqlalchemy import false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.layers.repository import LayerRepository
from app.features.layers.schemas import LayerSummary
from app.features.map_features.schemas import (
    FeatureGeometry,
    MapFeatureDetail,
    MapFeatureItem,
    MapFeatureSummary,
)
from app.features.workspaces.schemas import WorkspaceSelectionFilter
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
        workspace_filter: WorkspaceSelectionFilter | None = None,
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
                MapFeature.layer_id,
                MapFeature.source_feature_id,
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
        statement = self._apply_workspace_filter(statement, workspace_filter)
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
                    layer_id=int(row["layer_id"]),
                    source_feature_id=row["source_feature_id"],
                    geometry=FeatureGeometry.model_validate(geometry) if geometry else None,
                    properties=dict(row["properties"] or {}),
                )
            )
        next_cursor = str(rows[-1]["id"]) if has_more and rows else None
        return features, next_cursor, has_more

    async def list_feature_summaries(
        self,
        layer_id: int,
        limit: int,
        cursor: str | None,
        workspace_filter: WorkspaceSelectionFilter | None = None,
    ) -> tuple[list[MapFeatureSummary], str | None, bool]:
        if self.session is None:
            return [], None, False
        cursor_id = self._cursor_id(cursor)
        statement = (
            select(
                MapFeature.id,
                MapFeature.layer_id,
                MapFeature.source_feature_id,
                MapFeature.properties,
            )
            .where(MapFeature.layer_id == layer_id, MapFeature.id > cursor_id)
            .order_by(MapFeature.id)
            .limit(limit + 1)
        )
        statement = self._apply_workspace_filter(statement, workspace_filter)
        rows = (await self.session.execute(statement)).mappings().all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = [
            MapFeatureSummary(
                id=int(row["id"]),
                layer_id=int(row["layer_id"]),
                source_feature_id=row["source_feature_id"],
                label=self._feature_label(row["properties"], int(row["id"])),
                properties=dict(row["properties"] or {}),
            )
            for row in rows
        ]
        return items, str(rows[-1]["id"]) if has_more and rows else None, has_more

    async def get_feature_detail(
        self,
        layer_id: int,
        feature_id: int,
        workspace_filter: WorkspaceSelectionFilter | None = None,
    ) -> MapFeatureDetail | None:
        if self.session is None:
            return None
        statement = (
            select(
                MapFeature.id,
                MapFeature.layer_id,
                MapFeature.source_feature_id,
                MapFeature.properties,
                MapFeature.bbox,
                MapFeature.area,
                MapFeature.perimeter,
                MapFeature.revision,
                func.ST_AsGeoJSON(MapFeature.geom).label("geometry_json"),
                Layer,
            )
            .join(Layer, Layer.id == MapFeature.layer_id)
            .where(MapFeature.layer_id == layer_id, MapFeature.id == feature_id)
        )
        statement = self._apply_workspace_filter(statement, workspace_filter)
        row = (await self.session.execute(statement)).mappings().first()
        if row is None:
            return None
        raw_geometry = row["geometry_json"]
        geometry = json.loads(raw_geometry) if isinstance(raw_geometry, str) else raw_geometry
        return MapFeatureDetail(
            id=int(row["id"]),
            layer_id=int(row["layer_id"]),
            source_feature_id=row["source_feature_id"],
            geometry=FeatureGeometry.model_validate(geometry) if geometry else None,
            properties=dict(row["properties"] or {}),
            bbox=dict(row["bbox"] or {}),
            area=row["area"],
            perimeter=row["perimeter"],
            revision=int(row["revision"]),
            layer=LayerRepository.to_summary(row["Layer"]),
        )

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
                layer_id=layer.id,
                source_feature_id=feature.source_feature_id,
                geometry=FeatureGeometry.model_validate(mapping(polygon)),
                properties=dict(feature.properties or {}),
            ),
            LayerRepository.to_summary(layer),
        )

    @staticmethod
    def _cursor_id(cursor: str | None) -> int:
        if not cursor:
            return 0
        try:
            return int(cursor)
        except ValueError as exc:
            raise ValueError("cursor 必须是有效的要素 ID。") from exc

    @staticmethod
    def _apply_workspace_filter(statement, workspace_filter: WorkspaceSelectionFilter | None):
        if workspace_filter is None:
            return statement
        if not workspace_filter.visible:
            return statement.where(false())
        if workspace_filter.include_all:
            return statement
        conditions = []
        if workspace_filter.feature_ids:
            conditions.append(MapFeature.id.in_(workspace_filter.feature_ids))
        if workspace_filter.source_feature_ids:
            conditions.append(MapFeature.source_feature_id.in_(workspace_filter.source_feature_ids))
        return statement.where(or_(*conditions) if conditions else false())

    @staticmethod
    def _feature_label(properties: dict | None, feature_id: int) -> str:
        values = properties or {}
        for key in ("name", "名称", "title", "标题", "编号", "code"):
            value = values.get(key)
            if value not in (None, ""):
                return str(value)
        return f"图斑 {feature_id}"

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
