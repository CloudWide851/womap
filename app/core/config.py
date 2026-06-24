from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "WOMAP"
    app_version: str = "0.1.0"
    app_env: str = Field(default="local", validation_alias="APP_ENV")
    database_url: str = Field(
        default="sqlite+aiosqlite:///./womap.db",
        validation_alias="DATABASE_URL",
    )
    test_database_url: str = Field(
        default="sqlite+aiosqlite:///./womap_test.db",
        validation_alias="TEST_DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @computed_field
    @property
    def database_kind(self) -> str:
        if self.database_url.startswith("postgresql"):
            return "postgresql"
        if self.database_url.startswith("sqlite"):
            return "sqlite"
        return "unknown"


@lru_cache
def get_settings() -> Settings:
    return Settings()
