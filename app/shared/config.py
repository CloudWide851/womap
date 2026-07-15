from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field
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
        return bool(self.password_hash and not self.password_hash.startswith("replace-with-"))


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


class PerformanceSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    max_features_per_request: int = 5000
    default_bbox_limit: int = 1000
    simplify_tolerance: float = 0.00001
    cache_ttl_seconds: int = 120
    large_layer_feature_threshold: int = 50000
    tile_feature_threshold: int = 10000

    def clamp_feature_limit(self, requested_limit: int | None) -> int:
        if requested_limit is None:
            return self.default_bbox_limit
        return max(1, min(requested_limit, self.max_features_per_request))


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    app: AppSettings = Field(default_factory=AppSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    frontend: FrontendSettings = Field(default_factory=FrontendSettings)
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
