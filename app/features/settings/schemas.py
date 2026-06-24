from pydantic import BaseModel, Field


class RuntimePerformanceSettings(BaseModel):
    max_features_per_request: int
    default_bbox_limit: int
    simplify_tolerance: float
    cache_ttl_seconds: int
    large_layer_feature_threshold: int
    tile_feature_threshold: int


class RuntimeSettings(BaseModel):
    environment: str
    config_source: str
    database: str
    postgis_target: bool
    redis_configured: bool
    performance: RuntimePerformanceSettings
    panel_defaults: dict[str, bool] = Field(default_factory=dict)
