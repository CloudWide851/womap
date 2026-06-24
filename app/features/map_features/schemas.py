from typing import Any, Literal

from pydantic import BaseModel, Field

from app.shared.pagination import FeatureQueryMeta


class FeatureGeometry(BaseModel):
    type: str
    coordinates: Any


class MapFeatureItem(BaseModel):
    id: int
    geometry: FeatureGeometry | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class FeatureCollectionResponse(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[MapFeatureItem]
    meta: FeatureQueryMeta
