from app.features.layers.repository import LayerRepository
from app.features.layers.schemas import LayerCreate, LayerSummary
from app.shared.config import get_settings


class LayerService:
    def __init__(self, repository: LayerRepository | None = None) -> None:
        self.repository = repository or LayerRepository()
        self.settings = get_settings()

    async def list_layers(self) -> list[LayerSummary]:
        layers = await self.repository.list_summaries()
        for layer in layers:
            layer.performance.large_layer = (
                layer.feature_count >= self.settings.performance.large_layer_feature_threshold
            )
        return layers

    async def create_layer(self, payload: LayerCreate) -> LayerSummary:
        return await self.repository.create_manual_polygon_layer(payload.name)
