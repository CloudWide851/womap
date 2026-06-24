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


class DatabasePoolSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    min_size: int = 2
    max_size: int = 10
    timeout_seconds: int = 30


class DatabaseSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    driver: str = "postgresql+asyncpg"
    host: str = "localhost"
    port: int = 5432
    name: str = "womap"
    username: str = "womap"
    password: str = ""
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
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    test_database: TestDatabaseSettings = Field(default_factory=TestDatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    maps: MapsSettings = Field(default_factory=MapsSettings)
    performance: PerformanceSettings = Field(default_factory=PerformanceSettings)
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
