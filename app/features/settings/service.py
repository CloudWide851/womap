from app.features.settings.schemas import RuntimePerformanceSettings, RuntimeSettings
from app.shared.config import get_settings


class SettingsService:
    async def get_runtime_settings(self) -> RuntimeSettings:
        settings = get_settings()
        performance = settings.performance
        return RuntimeSettings(
            environment=settings.app.environment,
            config_source=settings.config_source,
            database=settings.database.kind,
            postgis_target=settings.database.uses_postgis,
            redis_configured=settings.redis.configured,
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
