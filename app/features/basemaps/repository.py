from app.features.basemaps.schemas import BasemapProvider
from app.shared.config import get_settings


class BasemapRepository:
    def list_enabled(self) -> list[BasemapProvider]:
        settings = get_settings()
        providers: list[BasemapProvider] = []
        for provider in settings.maps.enabled_providers:
            providers.append(
                BasemapProvider(
                    id=provider.id,
                    type=provider.type,
                    name=provider.name,
                    url_template=provider.url_template,
                    api_key=provider.api_key,
                    subdomains=provider.subdomains,
                    enabled=provider.enabled,
                    api_key_configured=bool(provider.api_key),
                )
            )
        return providers
