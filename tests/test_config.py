from pathlib import Path

import pytest

from app.shared.config import LOCAL_CONFIG_PATH
from app.shared.config import load_settings


def test_yaml_settings_loads_split_connection_fields() -> None:
    settings = load_settings()

    assert settings.app.name == "WOMAP"
    assert settings.database.host == "localhost"
    assert settings.redis.port == 6379
    assert settings.performance.default_bbox_limit == 1000


def test_database_url_encodes_special_password_without_manual_encoding(tmp_path: Path) -> None:
    config_path = tmp_path / "settings.yaml"
    config_path.write_text(
        """
app:
  name: WOMAP
database:
  driver: postgresql+asyncpg
  host: localhost
  port: 5432
  name: womap
  username: womap
  password: "p@ss:word/with#chars"
redis:
  host: localhost
  port: 6379
maps:
  providers: []
""",
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert str(settings.database.sqlalchemy_url()) == (
        "postgresql+asyncpg://womap:***@localhost:5432/womap"
    )
    assert settings.database.sqlalchemy_url().password == "p@ss:word/with#chars"


def test_runtime_feature_modules_import_cleanly() -> None:
    import app.features.basemaps.router
    import app.features.jobs.router
    import app.features.layers.router
    import app.features.map_features.router
    import app.features.projects.router
    import app.features.settings.router

    assert app.features.basemaps.router.router is not None


def test_local_yaml_settings_load_without_exposing_secrets() -> None:
    if not LOCAL_CONFIG_PATH.exists():
        pytest.skip("local yaml config is optional outside this workspace")

    settings = load_settings(LOCAL_CONFIG_PATH)
    redacted_summary = {
        "source": settings.config_source,
        "database": {
            "driver": settings.database.driver,
            "host": settings.database.host,
            "port": settings.database.port,
            "name": settings.database.name,
            "username_set": bool(settings.database.username),
            "password_set": bool(settings.database.password),
        },
        "redis": {
            "host": settings.redis.host,
            "port": settings.redis.port,
            "db": settings.redis.db,
            "username_set": bool(settings.redis.username),
            "password_set": bool(settings.redis.password),
        },
        "providers": [
            {
                "id": provider.id,
                "enabled": provider.enabled,
                "api_key_configured": bool(provider.api_key),
            }
            for provider in settings.maps.providers
        ],
        "performance": settings.performance.model_dump(),
    }

    assert redacted_summary["source"].endswith("settings.local.yaml")
    assert redacted_summary["database"]["driver"]
    assert redacted_summary["database"]["host"]
    assert redacted_summary["database"]["port"] > 0
    assert isinstance(redacted_summary["database"]["password_set"], bool)
    assert redacted_summary["redis"]["host"]
    assert redacted_summary["redis"]["port"] > 0
    assert len(redacted_summary["providers"]) > 0
    assert redacted_summary["performance"]["max_features_per_request"] >= 1
