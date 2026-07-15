from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FormulaNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["band", "number", "unary", "binary", "function"]
    band: int | None = None
    value: float | None = None
    operator: Literal["+", "-", "*", "/", "^"] | None = None
    name: Literal["abs", "sqrt", "log", "min", "max", "clamp"] | None = None
    argument: FormulaNode | None = None
    left: FormulaNode | None = None
    right: FormulaNode | None = None
    arguments: list[FormulaNode] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def validate_shape(self) -> FormulaNode:
        if self.kind == "band" and self.band is None:
            raise ValueError("band 节点缺少波段编号。")
        if self.kind == "number" and self.value is None:
            raise ValueError("number 节点缺少数值。")
        if self.kind == "unary" and (self.operator not in {"+", "-"} or self.argument is None):
            raise ValueError("unary 节点无效。")
        if self.kind == "binary" and (
            self.operator is None or self.left is None or self.right is None
        ):
            raise ValueError("binary 节点无效。")
        if self.kind == "function" and (self.name is None or not self.arguments):
            raise ValueError("function 节点无效。")
        return self


class RasterStyle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["womap.raster-style/v1"] = "womap.raster-style/v1"
    mode: Literal["rgb", "grayscale", "classified", "formula"] = "grayscale"
    bands: list[int] = Field(default_factory=lambda: [1], min_length=1, max_length=3)
    stretch: Literal["percentile", "minmax", "none"] = "percentile"
    min_values: list[float] = Field(default_factory=list, max_length=3)
    max_values: list[float] = Field(default_factory=list, max_length=3)
    gamma: float = Field(default=1.0, ge=0.1, le=5.0)
    nodata_transparent: bool = True
    color_ramp: str = "magma"
    class_breaks: list[float] = Field(default_factory=list, max_length=32)
    class_colors: list[str] = Field(default_factory=list, max_length=33)
    formula: FormulaNode | None = None


class RasterHistogramResponse(BaseModel):
    layer_id: int
    band: int
    bins: list[int]
    edges: list[float]
    minimum: float | None
    maximum: float | None
    percentiles: dict[str, float | None]
    sample_count: int


class RasterPixelResponse(BaseModel):
    layer_id: int
    x: float
    y: float
    crs: str
    values: list[float | int | None]
    nodata: bool


class RasterDeriveRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    formula: FormulaNode
    style: RasterStyle | None = None


class RasterExportRequest(BaseModel):
    format: Literal["cog", "geotiff"] = "cog"
    layer_ids: list[int] = Field(min_length=1, max_length=100)


class RasterStorageStatus(BaseModel):
    used_bytes: int
    quota_bytes: int
    available_bytes: int
    managed_assets: int
    orphan_assets: int
    scratch_bytes: int
    store_path: str
    scratch_path: str


class RasterCleanupResponse(BaseModel):
    deleted_assets: int
    freed_bytes: int
