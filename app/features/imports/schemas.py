from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ImportFormat = Literal["shp", "gdb", "tif", "img", "jp2", "vrt", "hdf", "netcdf"]
ImportState = Literal["unimported", "imported", "changed", "interrupted"]
DatasetKind = Literal["vector", "raster"]


class RasterBandMetadata(BaseModel):
    index: int
    name: str
    dtype: str
    nodata: float | int | None = None
    color_interpretation: str = "undefined"


class RasterMetadata(BaseModel):
    width: int
    height: int
    band_count: int
    driver: str
    dtypes: list[str] = Field(default_factory=list)
    nodata: list[float | int | None] = Field(default_factory=list)
    resolution: list[float] = Field(default_factory=list)
    byte_size: int = 0
    subdataset: str | None = None
    bands: list[RasterBandMetadata] = Field(default_factory=list)
    source_uri: str | None = Field(default=None, exclude=True)


class CatalogDataset(BaseModel):
    id: str
    source_id: str
    format: ImportFormat
    dataset_kind: DatasetKind = "vector"
    container: str
    relative_path: str
    layer_name: str
    geometry_type: str = "Unknown"
    feature_count: int = 0
    crs: str | None = None
    bounds: list[float] = Field(default_factory=list)
    fields: list[dict] = Field(default_factory=list)
    raster: RasterMetadata | None = None
    fingerprint: str
    valid: bool = True
    missing_required: list[str] = Field(default_factory=list)
    missing_optional: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    import_state: ImportState = "unimported"
    resumable_job_id: str | None = None


class ImportCatalog(BaseModel):
    source_id: str
    scanned_at: str
    datasets: list[CatalogDataset] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SyncRequest(BaseModel):
    source_id: str


class ImportRequest(BaseModel):
    source_id: str
    dataset_ids: list[str] = Field(min_length=1)
    crs_overrides: dict[str, str] = Field(default_factory=dict)
