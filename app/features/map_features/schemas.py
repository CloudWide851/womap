from typing import Any, Literal

from pydantic import BaseModel, Field

from app.features.layers.schemas import LayerSummary

from app.shared.pagination import FeatureQueryMeta


class FeatureGeometry(BaseModel):
    type: str
    coordinates: Any


class PolygonGeometry(BaseModel):
    type: Literal["Polygon"]
    coordinates: list[list[list[float]]]


class MapFeatureCreate(BaseModel):
    geometry: PolygonGeometry
    properties: dict[str, Any] = Field(default_factory=dict)


class MapFeatureItem(BaseModel):
    id: int
    geometry: FeatureGeometry | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class FeatureCollectionResponse(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[MapFeatureItem]
    meta: FeatureQueryMeta


class MapFeatureCreateResponse(BaseModel):
    feature: MapFeatureItem
    layer: LayerSummary
