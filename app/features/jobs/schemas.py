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


class RasterPhaseTimingsDetail(BaseModel):
    preflight: int = Field(default=0, ge=0)
    read_warp: int | None = Field(default=None, ge=0)
    compute: int | None = Field(default=None, ge=0)
    write_compress: int | None = Field(default=None, ge=0)
    overview: int | None = Field(default=None, ge=0)
    validation: int = Field(default=0, ge=0)
    combined_io: int | None = Field(default=None, ge=0)
    total: int = Field(default=0, ge=0)
    combined_phases: list[
        Literal["read_warp", "compute", "write_compress", "overview"]
    ] = Field(default_factory=list, max_length=4)
    backend_init: int | None = Field(default=None, ge=0)
    host_to_device: int | None = Field(default=None, ge=0)
    device_compute: int | None = Field(default=None, ge=0)
    device_to_host: int | None = Field(default=None, ge=0)


class RasterSpaceEstimateDetail(BaseModel):
    source: int = Field(default=0, ge=0)
    candidate_asset: int = Field(default=0, ge=0)
    formula_intermediate: int = Field(default=0, ge=0)
    compression_overview: int = Field(default=0, ge=0)
    final_asset: int = Field(default=0, ge=0)
    scratch_required: int = Field(default=0, ge=0)
    store_required: int = Field(default=0, ge=0)
    reserve: int = Field(default=0, ge=0)


class RasterFormulaBackendDetail(BaseModel):
    requested_backend: Literal["cpu", "auto", "cupy"]
    effective_backend: Literal["cpu", "cupy"]
    gate_status: Literal[
        "disabled", "unavailable", "missing", "rejected", "passed", "fallback"
    ]
    fallback_reason: str | None = Field(default=None, max_length=64)
    fallback_attempt_ms: int | None = Field(default=None, ge=0)
    max_batch_windows: int = Field(default=1, ge=1, le=64)


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
    phase_timings_ms: RasterPhaseTimingsDetail | None = None
    space_estimate_bytes: RasterSpaceEstimateDetail | None = None
    formula_backend: RasterFormulaBackendDetail | None = None
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


class VectorExportJobProgressDetail(BaseModel):
    kind: Literal["vector-export"] = "vector-export"
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
    | RasterExportJobProgressDetail
    | VectorExportJobProgressDetail,
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
