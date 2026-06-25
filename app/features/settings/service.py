from app.features.settings.schemas import RuntimeAuthSettings, RuntimePerformanceSettings, RuntimeSettings
from app.shared.config import get_settings


class SettingsService:
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
