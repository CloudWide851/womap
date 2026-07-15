from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from app.features.layers.schemas import LayerSummary


WORKSPACE_SCHEMA_VERSION = "womap.workspace/v1"
FeatureSelectionMode = Literal["all", "include"]


class WorkspaceFeatureSelection(BaseModel):
    mode: FeatureSelectionMode = "all"
    feature_ids: list[int] = Field(default_factory=list, max_length=10000)
    source_feature_ids: list[str] = Field(default_factory=list, max_length=10000)


class WorkspaceLayerConfig(BaseModel):
    layer_id: int = Field(gt=0)
    dataset_id: str | None = None
    visible: bool = True
    opacity: float = Field(default=1.0, ge=0, le=1)
    order: int = Field(default=0, ge=0)
    selection: WorkspaceFeatureSelection = Field(default_factory=WorkspaceFeatureSelection)


class WorkspaceMapView(BaseModel):
    center: tuple[float, float] = (12608500.0, 2644100.0)
    zoom: float = Field(default=10.0, ge=0, le=28)


class WorkspaceDefinition(BaseModel):
    schema_version: Literal["womap.workspace/v1"] = WORKSPACE_SCHEMA_VERSION
    workspace_uuid: str = Field(default_factory=lambda: str(uuid4()))
    revision: int = Field(default=1, ge=1)
    description: str = Field(default="", max_length=500)
    view: WorkspaceMapView = Field(default_factory=WorkspaceMapView)
    layers: list[WorkspaceLayerConfig] = Field(default_factory=list)


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    default_basemap: str = Field(default="osm", min_length=1, max_length=80)
    view: WorkspaceMapView = Field(default_factory=WorkspaceMapView)
    layers: list[WorkspaceLayerConfig] = Field(default_factory=list)

    @field_validator("name", "default_basemap")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("字段不能为空。")
        return normalized

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str) -> str:
        return value.strip()


class WorkspaceUpdate(WorkspaceCreate):
    revision: int = Field(ge=1)


class WorkspaceSummary(BaseModel):
    id: int
    name: str
    description: str = ""
    default_basemap: str
    revision: int
    layer_count: int
    is_default: bool = False
    updated_at: datetime | None = None


class WorkspaceLayerState(BaseModel):
    config: WorkspaceLayerConfig
    layer: LayerSummary


class WorkspaceDetail(WorkspaceSummary):
    schema_version: str = WORKSPACE_SCHEMA_VERSION
    workspace_uuid: str
    view: WorkspaceMapView
    layers: list[WorkspaceLayerState] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WorkspaceCatalogGroup(BaseModel):
    key: str
    label: str
    format: str
    source_id: str | None = None
    container: str | None = None
    layers: list[LayerSummary] = Field(default_factory=list)


class WorkspaceCatalogResponse(BaseModel):
    groups: list[WorkspaceCatalogGroup] = Field(default_factory=list)


class WorkspaceSelectionFilter(BaseModel):
    layer_id: int
    feature_ids: list[int] = Field(default_factory=list)
    source_feature_ids: list[str] = Field(default_factory=list)
    include_all: bool = True
    visible: bool = True


class WorkspaceBasemapReference(BaseModel):
    id: str
    name: str
    type: str


class WorkspacePackageLayerManifest(BaseModel):
    package_layer: str
    original_layer_id: int
    name: str
    geometry_type: str
    crs: str = "EPSG:3857"
    source_type: str
    feature_count: int = Field(ge=0)
    fields: list[dict[str, Any]] = Field(default_factory=list)
    field_mapping: dict[str, str] = Field(default_factory=dict)
    source_id: str | None = None
    dataset_id: str | None = None
    container: str | None = None
    fingerprint: str | None = None
    config: WorkspaceLayerConfig


class WorkspacePackageManifest(BaseModel):
    schema_version: Literal["womap.workspace/v1"] = WORKSPACE_SCHEMA_VERSION
    package_format: Literal["womap.package/v1"] = "womap.package/v1"
    workspace_name: str
    workspace_uuid: str
    revision: int = Field(ge=1)
    description: str = ""
    view: WorkspaceMapView
    basemap: WorkspaceBasemapReference
    layers: list[WorkspacePackageLayerManifest] = Field(default_factory=list)


class WorkspacePackagePreview(BaseModel):
    upload_token: str
    workspace_name: str
    workspace_uuid: str
    revision: int
    package_version: str
    layer_count: int
    feature_count: int
    basemap: WorkspaceBasemapReference
    basemap_missing: bool = False
    conflicting_workspace_id: int | None = None
    warnings: list[str] = Field(default_factory=list)


class WorkspacePackageImportRequest(BaseModel):
    upload_token: str = Field(min_length=16, max_length=80)
    strategy: Literal["copy", "replace"] = "copy"
    target_workspace_id: int | None = Field(default=None, gt=0)


class WorkspacePackageDownload(BaseModel):
    job_id: str
    filename: str
