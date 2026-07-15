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
    layer_id: int | None = None
    source_feature_id: str | None = None
    geometry: FeatureGeometry | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class MapFeatureDetail(MapFeatureItem):
    bbox: dict[str, float] = Field(default_factory=dict)
    area: float | None = None
    perimeter: float | None = None
    revision: int = 1
    layer: LayerSummary


class MapFeatureSummary(BaseModel):
    id: int
    layer_id: int
    source_feature_id: str | None = None
    label: str
    properties: dict[str, Any] = Field(default_factory=dict)


class MapFeatureSummaryPage(BaseModel):
    items: list[MapFeatureSummary] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False
    returned: int = 0


class FeatureCollectionResponse(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[MapFeatureItem]
    meta: FeatureQueryMeta


class MapFeatureCreateResponse(BaseModel):
    feature: MapFeatureItem
    layer: LayerSummary
