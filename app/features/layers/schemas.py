from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LayerCreate(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    geometry_type: Literal["Polygon"] = "Polygon"

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class LayerPerformanceState(BaseModel):
    feature_count: int = 0
    large_layer: bool = False
    indexed: bool = True
    recommended_mode: str = "bbox"
    warning: str | None = None


class LayerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    geometry_type: str
    feature_count: int
    crs: str | None = None
    bounds: dict = Field(default_factory=dict)
    visible: bool = True
    locked: bool = False
    opacity: float = 1.0
    source_type: str = "unknown"
    fields: list[dict] = Field(default_factory=list)
    style: dict = Field(default_factory=dict)
    performance: LayerPerformanceState = Field(default_factory=LayerPerformanceState)
