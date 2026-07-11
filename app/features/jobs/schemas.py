from typing import Literal

from pydantic import BaseModel, Field


JobState = Literal["queued", "running", "interrupted", "done", "failed", "unknown"]


class JobProgressDetail(BaseModel):
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


class JobStatus(BaseModel):
    id: str
    job_type: str = "unknown"
    status: JobState = "unknown"
    progress: int = 0
    message: str | None = "任务尚未接入执行队列。"
    detail: JobProgressDetail = Field(default_factory=JobProgressDetail)
    result: dict = Field(default_factory=dict)
