from typing import Annotated, Literal

from pydantic import BaseModel, Field


JobState = Literal["queued", "running", "interrupted", "done", "failed", "unknown"]


class JobProgressDetail(BaseModel):
    kind: Literal["import"] = "import"
    stage: str = "queued"
    source_id: str | None = None
    dataset_id: str | None = None
    dataset_name: str | None = None
    current_layer: str | None = None
    current_file: str | None = None
    imported_features: int = 0
    total_features: int = 0
    current_batch: int = 0
    total_batches: int = 0
    transferred_bytes: int = 0
    total_bytes: int = 0
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class WorkspacePackageJobProgressDetail(BaseModel):
    kind: Literal["workspace-package"] = "workspace-package"
    stage: str = "queued"
    operation: Literal["export", "import"] = "export"
    workspace_id: int | None = None
    current_layer: str | None = None
    processed_features: int = 0
    total_features: int = 0
    warnings: list[str] = Field(default_factory=list)
    artifact_name: str | None = None
    error: str | None = None


class SpatialAnalysisJobProgressDetail(BaseModel):
    kind: Literal["spatial-analysis"] = "spatial-analysis"
    stage: str = "queued"
    workspace_id: int | None = None
    target_feature_id: int | None = None
    processed_layers: int = 0
    total_layers: int = 0
    matched_features: int = 0
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class RasterJobProgressDetail(BaseModel):
    kind: Literal["raster-process"] = "raster-process"
    stage: str = "queued"
    operation: Literal["import", "derive"] = "import"
    source_id: str | None = None
    dataset_id: str | None = None
    layer_id: int | None = None
    dataset_name: str | None = None
    processed_bytes: int = 0
    total_bytes: int = 0
    processed_blocks: int = 0
    total_blocks: int = 0
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class RasterExportJobProgressDetail(BaseModel):
    kind: Literal["raster-export"] = "raster-export"
    stage: str = "queued"
    processed_layers: int = 0
    total_layers: int = 0
    artifact_name: str | None = None
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


JobDetail = Annotated[
    JobProgressDetail
    | WorkspacePackageJobProgressDetail
    | SpatialAnalysisJobProgressDetail
    | RasterJobProgressDetail
    | RasterExportJobProgressDetail,
    Field(discriminator="kind"),
]


class JobStatus(BaseModel):
    id: str
    job_type: str = "unknown"
    status: JobState = "unknown"
    progress: int = 0
    message: str | None = "任务尚未接入执行队列。"
    detail: JobDetail = Field(default_factory=JobProgressDetail)
    result: dict = Field(default_factory=dict)
