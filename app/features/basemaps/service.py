from app.features.basemaps.repository import BasemapRepository
from app.features.basemaps.schemas import BasemapProvider


class BasemapService:
    def __init__(self, repository: BasemapRepository | None = None) -> None:
        self.repository = repository or BasemapRepository()

    async def list_basemaps(self) -> list[BasemapProvider]:
        return self.repository.list_enabled()
