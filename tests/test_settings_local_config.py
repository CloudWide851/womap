from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.features.settings.schemas import (
    LocalFrontendDevServerSettings,
    LocalFrontendSettings,
    LocalRuntimeSettingsUpdate,
    LocalServerSettings,
)
from app.features.settings.service import SettingsService


def build_update(
    *,
    api_host: str = "127.0.0.2",
    api_port: int = 8100,
    web_host: str = "127.0.0.3",
    web_port: int = 5273,
) -> LocalRuntimeSettingsUpdate:
    return LocalRuntimeSettingsUpdate(
        server=LocalServerSettings(host=api_host, port=api_port),
        frontend=LocalFrontendSettings(
            dev_server=LocalFrontendDevServerSettings(host=web_host, port=web_port),
        ),
    )


@pytest.mark.asyncio
async def test_local_runtime_settings_write_only_updates_editable_runtime_fields(
    tmp_path: Path,
) -> None:
    local_path = tmp_path / "settings.local.yaml"
    local_path.write_text(
        """
app:
  name: WOMAP
server:
  host: 127.0.0.1
  port: 8000
frontend:
  dev_server:
    host: 127.0.0.1
    port: 5173
database:
  password: keep-secret
auth:
  local_user:
    password_hash: keep-hash
""",
        encoding="utf-8",
    )
    service = SettingsService(local_config_path=local_path, fallback_config_path=tmp_path / "missing.yaml")

    result = await service.update_local_runtime_settings(build_update())

    written = yaml.safe_load(local_path.read_text(encoding="utf-8"))
    assert result.config_source == str(local_path)
    assert result.local_config_path == str(local_path)
    assert result.server.host == "127.0.0.2"
    assert result.frontend.dev_server.port == 5273
    assert written["server"] == {"host": "127.0.0.2", "port": 8100}
    assert written["frontend"]["dev_server"] == {"host": "127.0.0.3", "port": 5273}
    assert written["database"]["password"] == "keep-secret"
    assert written["auth"]["local_user"]["password_hash"] == "keep-hash"


@pytest.mark.asyncio
async def test_local_runtime_settings_uses_example_as_base_when_local_is_missing(
    tmp_path: Path,
) -> None:
    local_path = tmp_path / "settings.local.yaml"
    example_path = tmp_path / "settings.example.yaml"
    example_path.write_text(
        """
server:
  host: 127.0.0.1
  port: 8000
frontend:
  dev_server:
    host: 127.0.0.1
    port: 5173
redis:
  password: null
""",
        encoding="utf-8",
    )
    service = SettingsService(local_config_path=local_path, fallback_config_path=example_path)

    await service.update_local_runtime_settings(build_update(api_port=8200, web_port=9273))

    written = yaml.safe_load(local_path.read_text(encoding="utf-8"))
    assert written["server"]["port"] == 8200
    assert written["frontend"]["dev_server"]["port"] == 9273
    assert written["redis"]["password"] is None


def test_local_runtime_settings_rejects_blank_host_and_invalid_port() -> None:
    with pytest.raises(ValidationError):
        build_update(api_host="   ")

    with pytest.raises(ValidationError):
        build_update(web_port=70000)
