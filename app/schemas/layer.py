from pydantic import BaseModel, ConfigDict


class LayerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    geometry_type: str
    feature_count: int
    visible: bool = True
    locked: bool = False
    opacity: float = 1.0
