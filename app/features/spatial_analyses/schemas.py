from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.features.jobs.schemas import JobStatus

AnalysisUnit = Literal["m", "km", "ft", "mi"]
AnalysisScope = Literal["all", "visible"]

UNIT_TO_METERS = {
    "m": 1.0,
    "km": 1000.0,
    "ft": 0.3048,
    "mi": 1609.344,
}


class SpatialAnalysisCreate(BaseModel):
    workspace_id: int = Field(gt=0)
    target_layer_id: int = Field(gt=0)
    target_feature_id: int = Field(gt=0)
    distance: float = Field(gt=0, le=1_000_000)
    unit: AnalysisUnit = "m"
    scope: AnalysisScope = "all"

    @property
    def distance_meters(self) -> float:
        return self.distance * UNIT_TO_METERS[self.unit]

    @model_validator(mode="after")
    def validate_distance_meters(self) -> "SpatialAnalysisCreate":
        if self.distance_meters > 2_000_000:
            raise ValueError("分析范围不能超过 2000 千米。")
        return self


class SpatialAnalysisLayerSummary(BaseModel):
    layer_id: int
    layer_name: str
    geometry_type: str
    exists: bool = False
    hit_count: int = 0
    nearest_distance_m: float | None = None
    direct_intersection_count: int = 0
    buffer_intersection_count: int = 0
    direct_area_sqm: float = 0
    buffer_area_sqm: float = 0
    direct_length_m: float = 0
    buffer_length_m: float = 0
    point_hit_count: int = 0
    coverage_ratio: float | None = None


class SpatialAnalysisDatasetSummary(BaseModel):
    key: str
    name: str
    source_type: str
    layers: list[SpatialAnalysisLayerSummary] = Field(default_factory=list)


class SpatialAnalysisHit(BaseModel):
    layer_id: int
    layer_name: str
    feature_id: int
    source_feature_id: str | None = None
    label: str
    geometry_type: str
    direct_intersection: bool
    buffer_intersection: bool
    distance_m: float
    intersection_area_sqm: float = 0
    intersection_length_m: float = 0
    properties: dict[str, Any] = Field(default_factory=dict)
    geometry: dict[str, Any] | None = None


class SpatialAnalysisHitPage(BaseModel):
    items: list[SpatialAnalysisHit] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False
    stale: bool = False
    warnings: list[str] = Field(default_factory=list)


class SpatialAnalysisResult(BaseModel):
    job: JobStatus
    workspace_id: int
    target_layer_id: int
    target_feature_id: int
    distance: float
    unit: AnalysisUnit
    distance_meters: float
    scope: AnalysisScope
    target_geometry: dict[str, Any] | None = None
    buffer_geometry: dict[str, Any] | None = None
    groups: list[SpatialAnalysisDatasetSummary] = Field(default_factory=list)
    stale: bool = False
    warnings: list[str] = Field(default_factory=list)
