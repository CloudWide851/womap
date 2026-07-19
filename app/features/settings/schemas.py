from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LocalServerSettings(BaseModel):
    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)

    @field_validator("host")
    @classmethod
    def normalize_host(cls, value: str) -> str:
        host = value.strip()
        if not host:
            raise ValueError("host must not be blank")
        return host


class LocalFrontendDevServerSettings(BaseModel):
    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)

    @field_validator("host")
    @classmethod
    def normalize_host(cls, value: str) -> str:
        host = value.strip()
        if not host:
            raise ValueError("host must not be blank")
        return host


class LocalFrontendSettings(BaseModel):
    dev_server: LocalFrontendDevServerSettings


class LocalRuntimeSettings(BaseModel):
    config_source: str
    local_config_path: str
    server: LocalServerSettings
    frontend: LocalFrontendSettings


class LocalRuntimeSettingsUpdate(BaseModel):
    server: LocalServerSettings
    frontend: LocalFrontendSettings


class ImportSourceBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["local", "smb"]
    root_path: str = ""
    server: str = ""
    share: str = ""
    base_path: str = ""
    username: str = ""
    domain: str = ""
    port: int = Field(default=445, ge=1, le=65535)
    encrypt: bool = True
    enabled: bool = True

    @field_validator("name", "root_path", "server", "share", "base_path", "username", "domain")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class ImportSourceCreate(ImportSourceBase):
    password: str | None = Field(default=None, max_length=512)


class ImportSourceUpdate(ImportSourceBase):
    password: str | None = Field(default=None, max_length=512)


class ImportSourceResponse(ImportSourceBase):
    id: str
    credential_configured: bool = False


class ImportSourceTestRequest(BaseModel):
    password: str | None = Field(default=None, max_length=512)


class ImportSourceTestResponse(BaseModel):
    ok: bool
    message: str


class ImportSettingsResponse(BaseModel):
    cache_path: str
    batch_size: int
    raster_store_path: str
    raster_scratch_path: str
    raster_quota_gb: int
    sources: list[ImportSourceResponse]


class ImportOptionsUpdate(BaseModel):
    cache_path: str = Field(min_length=1, max_length=500)
    batch_size: int = Field(ge=100, le=20000)
    raster_store_path: str = Field(default=".womap-data/rasters", min_length=1, max_length=500)
    raster_scratch_path: str = Field(
        default=".womap-data/raster-scratch", min_length=1, max_length=500
    )
    raster_quota_gb: int = Field(default=200, ge=1, le=16384)


class RuntimePerformanceSettings(BaseModel):
    profile: Literal["auto", "low", "balanced", "high"]
    enforcement: Literal["active"] = "active"
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
