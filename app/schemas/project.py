from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProjectSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    updated_at: datetime | None = None
