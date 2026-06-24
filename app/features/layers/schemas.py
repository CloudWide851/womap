from pydantic import BaseModel, ConfigDict, Field


class LayerPerformanceState(BaseModel):
    feature_count: int = 0
    large_layer: bool = False
    indexed: bool = True
    recommended_mode: str = "bbox"
    warning: str | None = None


class LayerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    geometry_type: str
    feature_count: int
    crs: str | None = None
    bounds: dict = Field(default_factory=dict)
    visible: bool = True
    locked: bool = False
    opacity: float = 1.0
    performance: LayerPerformanceState = Field(default_factory=LayerPerformanceState)
