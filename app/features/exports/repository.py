from __future__ import annotations

import json
from collections import OrderedDict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.exports.schemas import ExportFeature, ExportLayer
from app.models.layer import Layer
from app.models.map_feature import MapFeature


class ExportRepository:
    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session

    async def list_layers_for_export(self, layer_ids: list[int]) -> list[ExportLayer]:
        if self.session is None or not layer_ids:
            return []

        stmt = (
            select(
                Layer.id.label("layer_id"),
                Layer.name.label("layer_name"),
                Layer.geometry_type,
                Layer.crs,
                MapFeature.id.label("feature_id"),
                MapFeature.properties,
                func.ST_AsGeoJSON(MapFeature.geom).label("geometry_json"),
            )
            .join(MapFeature, MapFeature.layer_id == Layer.id)
            .where(Layer.id.in_(layer_ids))
            .order_by(Layer.id, MapFeature.id)
        )
        rows = (await self.session.execute(stmt)).mappings().all()
        grouped: OrderedDict[int, ExportLayer] = OrderedDict()

        for row in rows:
            geometry = self._parse_geometry(row["geometry_json"])
            if geometry is None:
                continue

            layer_id = int(row["layer_id"])
            if layer_id not in grouped:
                grouped[layer_id] = ExportLayer(
                    id=layer_id,
                    name=str(row["layer_name"]),
                    geometry_type=str(row["geometry_type"]),
                    crs=row["crs"] or "EPSG:3857",
                    features=[],
                )

            grouped[layer_id].features.append(
                ExportFeature(
                    id=int(row["feature_id"]),
                    geometry=geometry,
                    properties=dict(row["properties"] or {}),
                ),
            )

        return [layer for layer in grouped.values() if layer.features]

    async def raster_layer_ids(self, layer_ids: list[int]) -> list[int]:
        if self.session is None or not layer_ids:
            return []
        values = await self.session.scalars(
            select(Layer.id).where(
                Layer.id.in_(layer_ids),
                Layer.geometry_type == "Raster",
            )
        )
        return [int(value) for value in values]

    def _parse_geometry(self, value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        if isinstance(value, str):
            parsed = json.loads(value)
        else:
            parsed = value
        if not isinstance(parsed, dict):
            return None
        return parsed
