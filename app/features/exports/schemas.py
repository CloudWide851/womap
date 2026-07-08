from typing import Any, Literal

from pydantic import BaseModel, Field


ExportFormat = Literal["shp", "gdb"]


class ExportRequest(BaseModel):
    format: ExportFormat
    layer_ids: list[int] = Field(default_factory=list)


class ExportFeature(BaseModel):
    id: int
    geometry: dict[str, Any]
    properties: dict[str, Any] = Field(default_factory=dict)


class ExportLayer(BaseModel):
    id: int
    name: str
    geometry_type: str
    crs: str | None = "EPSG:3857"
    features: list[ExportFeature]
