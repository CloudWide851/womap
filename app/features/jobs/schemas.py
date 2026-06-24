from pydantic import BaseModel, Field


class JobStatus(BaseModel):
    id: str
    job_type: str = "unknown"
    status: str = "unknown"
    progress: int = 0
    message: str | None = "任务尚未接入执行队列。"
    result: dict = Field(default_factory=dict)
