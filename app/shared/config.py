from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import URL


ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT_DIR / "config"
LOCAL_CONFIG_PATH = CONFIG_DIR / "settings.local.yaml"
EXAMPLE_CONFIG_PATH = CONFIG_DIR / "settings.example.yaml"


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = "WOMAP"
    version: str = "0.1.0"
    environment: str = "local"
    debug: bool = False


class ServerSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


class FrontendDevServerSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    host: str = "127.0.0.1"
    port: int = 5173


class FrontendSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dev_server: FrontendDevServerSettings = Field(default_factory=FrontendDevServerSettings)


class ApplicationRuntimeSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mode: Literal["development", "production"] = "development"


class DatabasePoolSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    min_size: int = 2
    max_size: int = 10
    timeout_seconds: int = 30


class DatabaseSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    driver: str = "postgresql+asyncpg"
    host: str = "127.0.0.1"
    port: int = 5432
    name: str = "womap"
    username: str = "womap"
    password: str = ""
    ssl: bool = False
    pool: DatabasePoolSettings = Field(default_factory=DatabasePoolSettings)

    def sqlalchemy_url(self) -> URL:
        return URL.create(
            drivername=self.driver,
            username=self.username or None,
            password=self.password or None,
            host=self.host or None,
            port=self.port or None,
            database=self.name or None,
        )

    def connect_args(self) -> dict[str, Any]:
        if self.driver == "postgresql+asyncpg":
            return {"ssl": self.ssl}
        return {}

    @property
    def kind(self) -> str:
        if self.driver.startswith("postgresql"):
            return "postgresql"
        if self.driver.startswith("sqlite"):
            return "sqlite"
        return self.driver.split("+", maxsplit=1)[0]

    @property
    def uses_postgis(self) -> bool:
        return self.kind == "postgresql"


class TestDatabaseSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    driver: str = "sqlite+aiosqlite"
    path: str = "./womap_test.db"

    def sqlalchemy_url(self) -> URL:
        return URL.create(drivername=self.driver, database=self.path)


class ImportSourceSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    kind: Literal["local", "smb"] = "local"
    root_path: str = ""
    server: str = ""
    share: str = ""
    base_path: str = ""
    username: str = ""
    domain: str = ""
    port: int = 445
    encrypt: bool = True
    enabled: bool = True


class ImportsSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    cache_path: str = ".womap-data/import-cache"
    batch_size: int = Field(default=2000, ge=100, le=20000)
    raster_store_path: str = ".womap-data/rasters"
    raster_scratch_path: str = ".womap-data/raster-scratch"
    raster_quota_gb: int = Field(default=200, ge=1, le=16384)
    sources: list[ImportSourceSettings] = Field(default_factory=list)


class RedisSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    username: str | None = None
    password: str | None = None
    socket_timeout_seconds: int = 5

    def connection_kwargs(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "db": self.db,
            "username": self.username,
            "password": self.password,
            "socket_timeout": self.socket_timeout_seconds,
            "decode_responses": True,
        }

    @property
    def configured(self) -> bool:
        return bool(self.host and self.port)


class LocalUserAuthSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    username: str = "local-admin"
    password_hash: str = ""
    password_hash_algorithm: Literal["pbkdf2_sha256"] = "pbkdf2_sha256"

    @property
    def password_configured(self) -> bool:
        return is_password_hash_configured(self.password_hash)


def is_password_hash_configured(value: str) -> bool:
    return bool(value and not value.startswith("replace-with-"))


class PasswordPolicySettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    min_length: int = 15
    max_length: int = 128
    block_common_passwords: bool = True


class SessionSecuritySettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    idle_timeout_minutes: int = 30
    absolute_timeout_hours: int = 12
    renewal_timeout_minutes: int = 30
    remember_me_days: int = 7
    cookie_name: str = "womap_session"
    secure_cookie: bool = True
    http_only_cookie: bool = True
    same_site: Literal["lax", "strict", "none"] = "lax"

    @model_validator(mode="after")
    def require_secure_cookie_for_same_site_none(self) -> "SessionSecuritySettings":
        if self.same_site == "none" and not self.secure_cookie:
            raise ValueError("SameSite=None requires a secure session cookie")
        return self


class AuthThrottleSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    lockout_attempts: int = 5
    lockout_window_minutes: int = 15


class AuthDynamicUpdateSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    policy_refresh_seconds: int = 30
    warn_before_expire_minutes: int = 5
    rotate_after_login: bool = True


class AuthAuditSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    log_login_events: bool = True
    redact_session_id: bool = True


class AuthSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    local_user: LocalUserAuthSettings = Field(default_factory=LocalUserAuthSettings)
    password_policy: PasswordPolicySettings = Field(default_factory=PasswordPolicySettings)
    session: SessionSecuritySettings = Field(default_factory=SessionSecuritySettings)
    throttling: AuthThrottleSettings = Field(default_factory=AuthThrottleSettings)
    dynamic_update: AuthDynamicUpdateSettings = Field(default_factory=AuthDynamicUpdateSettings)
    audit: AuthAuditSettings = Field(default_factory=AuthAuditSettings)


class MapProviderSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    type: Literal["xyz", "wms"] = "xyz"
    name: str
    url_template: str
    api_key: str = ""
    subdomains: list[str] = Field(default_factory=list)
    enabled: bool = True


class MapsSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    providers: list[MapProviderSettings] = Field(default_factory=list)

    @property
    def enabled_providers(self) -> list[MapProviderSettings]:
        return [provider for provider in self.providers if provider.enabled]


class PerformanceApiSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    worker_count: int = Field(default=1, ge=1, le=4)
    database_pool_size: int | None = Field(default=None, ge=1, le=32)
    database_max_overflow: int | None = Field(default=None, ge=0, le=32)
    database_timeout_seconds: int = Field(default=30, ge=1, le=120)
    database_recycle_seconds: int = Field(default=1800, ge=60, le=86400)


class PerformanceWorkerSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    concurrency: int | None = Field(default=None, ge=1, le=4)
    poll_interval_seconds: float = Field(default=1.0, ge=0.1, le=30)
    lease_seconds: int = Field(default=120, ge=30, le=3600)
    heartbeat_seconds: int = Field(default=30, ge=5, le=600)
    shutdown_grace_seconds: int = Field(default=30, ge=1, le=300)


class PerformanceGdalSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    cache_mib: int | None = Field(default=None, ge=64, le=4096)
    thread_cap: int | None = Field(default=None, ge=1, le=32)
    dataset_pool_size: int | None = Field(default=None, ge=8, le=256)
    formula_window_budget_mib: int | None = Field(default=None, ge=32, le=2048)
    scratch_reserve_gib: int = Field(default=5, ge=1, le=1024)


class PerformanceBrowserSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vector_limit: int | None = Field(default=None, ge=100, le=5000)
    bbox_debounce_ms: int | None = Field(default=None, ge=50, le=2000)
    webgl_texture_cache: int | None = Field(default=None, ge=32, le=1024)
    geotiff_cache_size: int | None = Field(default=None, ge=8, le=256)


class PerformanceCacheSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    namespace: str = Field(default="womap:performance", min_length=1, max_length=64)
    ttl_seconds: int = Field(default=120, ge=1, le=86400)
    max_entry_kib: int = Field(default=256, ge=1, le=4096)
    fail_open: bool = True


class PerformanceGpuSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    backend: Literal["cpu", "auto", "cupy"] = "cpu"
    device_index: int = Field(default=0, ge=0, le=15)
    memory_fraction: float = Field(default=0.5, ge=0.1, le=0.9)
    minimum_speedup: float = Field(default=1.5, ge=1.0, le=10.0)


class ResolvedPerformanceSettings(BaseModel):
    requested_profile: Literal["auto", "low", "balanced", "high"]
    resolved_profile: Literal["low", "balanced", "high"]
    resolution_reason: str
    enforcement: Literal["diagnostic"] = "diagnostic"
    api_worker_count: int
    database_pool_size: int
    database_max_overflow: int
    worker_enabled: bool
    worker_concurrency: int
    gdal_cache_mib: int
    gdal_threads: int
    gdal_dataset_pool_size: int
    formula_window_budget_mib: int
    scratch_reserve_gib: int
    browser_vector_limit: int
    browser_bbox_debounce_ms: int
    webgl_texture_cache: int
    geotiff_cache_size: int
    cache_enabled: bool
    cache_ttl_seconds: int
    cache_max_entry_kib: int
    gpu_requested_backend: Literal["cpu", "auto", "cupy"]
    gpu_memory_fraction: float
    gpu_minimum_speedup: float


class PerformanceSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    profile: Literal["auto", "low", "balanced", "high"] = "auto"
    max_features_per_request: int = 5000
    default_bbox_limit: int = 1000
    simplify_tolerance: float = 0.00001
    cache_ttl_seconds: int = 120
    large_layer_feature_threshold: int = 50000
    tile_feature_threshold: int = 10000
    api: PerformanceApiSettings = Field(default_factory=PerformanceApiSettings)
    worker: PerformanceWorkerSettings = Field(default_factory=PerformanceWorkerSettings)
    gdal: PerformanceGdalSettings = Field(default_factory=PerformanceGdalSettings)
    browser: PerformanceBrowserSettings = Field(default_factory=PerformanceBrowserSettings)
    cache: PerformanceCacheSettings = Field(default_factory=PerformanceCacheSettings)
    gpu: PerformanceGpuSettings = Field(default_factory=PerformanceGpuSettings)

    def clamp_feature_limit(self, requested_limit: int | None) -> int:
        if requested_limit is None:
            return self.default_bbox_limit
        return max(1, min(requested_limit, self.max_features_per_request))

    def resolve(
        self,
        *,
        logical_cpu_count: int | None,
        total_memory_bytes: int | None,
    ) -> ResolvedPerformanceSettings:
        logical_cpus = max(1, logical_cpu_count or 1)
        memory_gib = max(1.0, (total_memory_bytes or 0) / (1024**3))

        resolved_profile: Literal["low", "balanced", "high"]
        reason: str
        if self.profile != "auto":
            resolved_profile = self.profile
            reason = "explicit_profile"
        elif logical_cpus <= 4 or memory_gib < 8:
            resolved_profile = "low"
            reason = "auto_limited_resources"
        elif logical_cpus >= 16 and memory_gib >= 32:
            resolved_profile = "high"
            reason = "auto_workstation_resources"
        else:
            resolved_profile = "balanced"
            reason = "auto_balanced_resources"

        presets = {
            "low": {
                "pool_size": 4,
                "overflow": 1,
                "gdal_threads": 1,
                "gdal_cache": 128,
                "dataset_pool": 32,
                "formula_budget": 64,
                "vector_limit": min(1000, self.default_bbox_limit),
                "debounce": 260,
                "texture_cache": 128,
                "geotiff_cache": 32,
            },
            "balanced": {
                "pool_size": 8,
                "overflow": 2,
                "gdal_threads": max(1, min(4, logical_cpus - 1)),
                "gdal_cache": max(128, min(512, int(memory_gib * 16))),
                "dataset_pool": 64,
                "formula_budget": 128,
                "vector_limit": min(2000, self.max_features_per_request),
                "debounce": 180,
                "texture_cache": 256,
                "geotiff_cache": 48,
            },
            "high": {
                "pool_size": 12,
                "overflow": 4,
                "gdal_threads": max(1, min(8, logical_cpus - 2)),
                "gdal_cache": max(256, min(1024, int(memory_gib * 24))),
                "dataset_pool": 128,
                "formula_budget": 256,
                "vector_limit": min(3000, self.max_features_per_request),
                "debounce": 140,
                "texture_cache": 384,
                "geotiff_cache": 64,
            },
        }
        preset = presets[resolved_profile]

        return ResolvedPerformanceSettings(
            requested_profile=self.profile,
            resolved_profile=resolved_profile,
            resolution_reason=reason,
            api_worker_count=self.api.worker_count,
            database_pool_size=self.api.database_pool_size or preset["pool_size"],
            database_max_overflow=(
                self.api.database_max_overflow
                if self.api.database_max_overflow is not None
                else preset["overflow"]
            ),
            worker_enabled=self.worker.enabled,
            worker_concurrency=self.worker.concurrency or 1,
            gdal_cache_mib=self.gdal.cache_mib or preset["gdal_cache"],
            gdal_threads=self.gdal.thread_cap or preset["gdal_threads"],
            gdal_dataset_pool_size=self.gdal.dataset_pool_size or preset["dataset_pool"],
            formula_window_budget_mib=(
                self.gdal.formula_window_budget_mib or preset["formula_budget"]
            ),
            scratch_reserve_gib=self.gdal.scratch_reserve_gib,
            browser_vector_limit=self.browser.vector_limit or preset["vector_limit"],
            browser_bbox_debounce_ms=self.browser.bbox_debounce_ms or preset["debounce"],
            webgl_texture_cache=self.browser.webgl_texture_cache or preset["texture_cache"],
            geotiff_cache_size=self.browser.geotiff_cache_size or preset["geotiff_cache"],
            cache_enabled=self.cache.enabled,
            cache_ttl_seconds=self.cache.ttl_seconds,
            cache_max_entry_kib=self.cache.max_entry_kib,
            gpu_requested_backend=self.gpu.backend,
            gpu_memory_fraction=self.gpu.memory_fraction,
            gpu_minimum_speedup=self.gpu.minimum_speedup,
        )


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    app: AppSettings = Field(default_factory=AppSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    frontend: FrontendSettings = Field(default_factory=FrontendSettings)
    runtime: ApplicationRuntimeSettings = Field(default_factory=ApplicationRuntimeSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    test_database: TestDatabaseSettings = Field(default_factory=TestDatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    maps: MapsSettings = Field(default_factory=MapsSettings)
    performance: PerformanceSettings = Field(default_factory=PerformanceSettings)
    imports: ImportsSettings = Field(default_factory=ImportsSettings)
    config_source: str = "defaults"


def resolve_config_path(config_path: str | Path | None = None) -> Path:
    if config_path is not None:
        return Path(config_path)
    if LOCAL_CONFIG_PATH.exists():
        return LOCAL_CONFIG_PATH
    return EXAMPLE_CONFIG_PATH


def load_settings(config_path: str | Path | None = None) -> Settings:
    resolved_path = resolve_config_path(config_path)
    raw_config: dict[str, Any] = {}
    if resolved_path.exists():
        with resolved_path.open("r", encoding="utf-8") as config_file:
            raw_config = yaml.safe_load(config_file) or {}
    settings = Settings.model_validate(raw_config)
    settings.config_source = str(resolved_path)
    return settings


@lru_cache
def get_settings() -> Settings:
    return load_settings()
