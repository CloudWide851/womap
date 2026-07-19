from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.sql import Select

from app.models.map_feature import MapFeature
from app.shared.pagination import BBoxQuery


def build_viewport_feature_statement(
    *,
    layer_id: int,
    bbox: BBoxQuery,
    cursor_id: int,
    simplify: float | None,
    row_limit: int,
) -> Select:
    """Single production boundary reused by the API and EXPLAIN collector."""
    envelope = func.ST_MakeEnvelope(*bbox.as_tuple(), 3857)
    geometry_expression = MapFeature.geom
    if simplify and simplify > 0:
        geometry_expression = func.ST_SimplifyPreserveTopology(MapFeature.geom, simplify)
    return (
        select(
            MapFeature.id,
            MapFeature.layer_id,
            MapFeature.source_feature_id,
            MapFeature.properties,
            MapFeature.revision,
            func.ST_AsGeoJSON(geometry_expression).label("geometry_json"),
        )
        .where(
            MapFeature.layer_id == layer_id,
            MapFeature.id > cursor_id,
            func.ST_Intersects(MapFeature.geom, envelope),
        )
        .order_by(MapFeature.id)
        .limit(row_limit)
    )
