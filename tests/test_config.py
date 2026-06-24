from pathlib import Path

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
