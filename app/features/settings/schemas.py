from pydantic import BaseModel, Field


class RuntimePerformanceSettings(BaseModel):
    max_features_per_request: int
    default_bbox_limit: int
    simplify_tolerance: float
    cache_ttl_seconds: int
    large_layer_feature_threshold: int
    tile_feature_threshold: int


class RuntimeAuthSettings(BaseModel):
    enabled: bool
    credential_configured: bool
    password_min_length: int
    password_max_length: int
    idle_timeout_minutes: int
    absolute_timeout_hours: int
    renewal_timeout_minutes: int
    remember_me_days: int
    policy_refresh_seconds: int
    warn_before_expire_minutes: int


class RuntimeSettings(BaseModel):
    environment: str
    config_source: str
    database: str
    postgis_target: bool
    redis_configured: bool
    auth: RuntimeAuthSettings
    performance: RuntimePerformanceSettings
    panel_defaults: dict[str, bool] = Field(default_factory=dict)
