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


class LayerProvenance(BaseModel):
    source_id: str | None = None
    dataset_id: str | None = None
    format: str = "manual"
    container: str | None = None
    relative_path: str | None = None
    layer_name: str | None = None
    fingerprint: str | None = None


class RasterLayerBand(BaseModel):
    index: int
    name: str
    dtype: str
    nodata: float | int | None = None
    color_interpretation: str = "undefined"


class RasterLayerMetadata(BaseModel):
    width: int
    height: int
    band_count: int
    driver: str = "GTiff"
    dtypes: list[str] = Field(default_factory=list)
    nodata: list[float | int | None] = Field(default_factory=list)
    resolution: list[float] = Field(default_factory=list)
    byte_size: int = 0
    bands: list[RasterLayerBand] = Field(default_factory=list)
    asset_url: str
    fingerprint: str


class LayerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: Literal["vector", "raster"] = "vector"
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
    provenance: LayerProvenance = Field(default_factory=LayerProvenance)
    raster: RasterLayerMetadata | None = None
