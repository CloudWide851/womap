from sqlalchemy.ext.asyncio import AsyncSession

from app.features.layers.schemas import LayerSummary


class LayerRepository:
    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session

    async def list_summaries(self) -> list[LayerSummary]:
        return []
