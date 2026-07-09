from pathlib import Path
from typing import Any

import yaml

from app.features.settings.schemas import (
    LocalFrontendDevServerSettings,
    LocalFrontendSettings,
    LocalRuntimeSettings,
    LocalRuntimeSettingsUpdate,
    LocalServerSettings,
    RuntimeAuthSettings,
    RuntimePerformanceSettings,
    RuntimeSettings,
)
from app.shared.config import EXAMPLE_CONFIG_PATH, LOCAL_CONFIG_PATH, get_settings, load_settings


class SettingsService:
    def __init__(
        self,
        local_config_path: Path = LOCAL_CONFIG_PATH,
        fallback_config_path: Path = EXAMPLE_CONFIG_PATH,
    ) -> None:
        self.local_config_path = local_config_path
        self.fallback_config_path = fallback_config_path

    async def get_runtime_settings(self) -> RuntimeSettings:
        settings = get_settings()
        performance = settings.performance
        auth = settings.auth
        return RuntimeSettings(
            environment=settings.app.environment,
            config_source=settings.config_source,
            database=settings.database.kind,
            postgis_target=settings.database.uses_postgis,
            redis_configured=settings.redis.configured,
            auth=RuntimeAuthSettings(
                enabled=auth.enabled,
                credential_configured=auth.local_user.password_configured,
                password_min_length=auth.password_policy.min_length,
                password_max_length=auth.password_policy.max_length,
                idle_timeout_minutes=auth.session.idle_timeout_minutes,
                absolute_timeout_hours=auth.session.absolute_timeout_hours,
                renewal_timeout_minutes=auth.session.renewal_timeout_minutes,
                remember_me_days=auth.session.remember_me_days,
                policy_refresh_seconds=auth.dynamic_update.policy_refresh_seconds,
                warn_before_expire_minutes=auth.dynamic_update.warn_before_expire_minutes,
            ),
            performance=RuntimePerformanceSettings(
                max_features_per_request=performance.max_features_per_request,
                default_bbox_limit=performance.default_bbox_limit,
                simplify_tolerance=performance.simplify_tolerance,
                cache_ttl_seconds=performance.cache_ttl_seconds,
                large_layer_feature_threshold=performance.large_layer_feature_threshold,
                tile_feature_threshold=performance.tile_feature_threshold,
            ),
            panel_defaults={
                "layers": True,
                "basemaps": True,
                "jobs": True,
                "properties": True,
                "fields": True,
                "performance": True,
            },
        )

    async def get_local_runtime_settings(self) -> LocalRuntimeSettings:
        config_path = (
            self.local_config_path if self.local_config_path.exists() else self.fallback_config_path
        )
        settings = load_settings(config_path)
        return LocalRuntimeSettings(
            config_source=settings.config_source,
            local_config_path=str(self.local_config_path),
            server=LocalServerSettings(host=settings.server.host, port=settings.server.port),
            frontend=LocalFrontendSettings(
                dev_server=LocalFrontendDevServerSettings(
                    host=settings.frontend.dev_server.host,
                    port=settings.frontend.dev_server.port,
                ),
            ),
        )

    async def update_local_runtime_settings(
        self, payload: LocalRuntimeSettingsUpdate
    ) -> LocalRuntimeSettings:
        raw_config = self._read_edit_base()
        server_config = self._ensure_mapping(raw_config, "server")
        frontend_config = self._ensure_mapping(raw_config, "frontend")
        dev_server_config = self._ensure_mapping(frontend_config, "dev_server")

        server_config["host"] = payload.server.host
        server_config["port"] = payload.server.port
        dev_server_config["host"] = payload.frontend.dev_server.host
        dev_server_config["port"] = payload.frontend.dev_server.port

        self.local_config_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.local_config_path.with_suffix(".tmp")
        with temporary_path.open("w", encoding="utf-8") as config_file:
            yaml.safe_dump(raw_config, config_file, allow_unicode=True, sort_keys=False)
        temporary_path.replace(self.local_config_path)
        get_settings.cache_clear()
        return await self.get_local_runtime_settings()

    def _read_edit_base(self) -> dict[str, Any]:
        config_path = (
            self.local_config_path if self.local_config_path.exists() else self.fallback_config_path
        )
        if not config_path.exists():
            return {}
        with config_path.open("r", encoding="utf-8") as config_file:
            loaded_config = yaml.safe_load(config_file) or {}
        if not isinstance(loaded_config, dict):
            return {}
        return loaded_config

    @staticmethod
    def _ensure_mapping(config: dict[str, Any], key: str) -> dict[str, Any]:
        section = config.get(key)
        if not isinstance(section, dict):
            section = {}
            config[key] = section
        return section
