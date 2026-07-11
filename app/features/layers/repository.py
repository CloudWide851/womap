from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.layers.schemas import LayerPerformanceState, LayerSummary
from app.models.layer import Layer


class LayerRepository:
    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session

    async def list_summaries(self) -> list[LayerSummary]:
        if self.session is None:
            return []
        layers = (
            await self.session.scalars(
                select(Layer).where(Layer.visible.is_(True)).order_by(Layer.created_at, Layer.id)
            )
        ).all()
        summaries: list[LayerSummary] = []
        for layer in layers:
            metadata = dict(layer.performance or {})
            if metadata.get("staging"):
                continue
            summaries.append(
                LayerSummary(
                    id=layer.id,
                    name=layer.name,
                    geometry_type=layer.geometry_type,
                    feature_count=layer.feature_count,
                    crs=layer.crs,
                    bounds=dict(layer.bounds or {}),
                    visible=layer.visible,
                    locked=layer.locked,
                    opacity=layer.opacity,
                    fields=list(layer.fields or []),
                    style=dict(layer.style or {}),
                    source_type=layer.source_type,
                    performance=LayerPerformanceState.model_validate(metadata),
                )
            )
        return summaries
