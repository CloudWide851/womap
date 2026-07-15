from pathlib import Path, PureWindowsPath

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.layers.schemas import LayerPerformanceState, LayerProvenance, LayerSummary
from app.features.projects.repository import ProjectRepository
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
            summaries.append(self.to_summary(layer, metadata))
        return summaries

    async def create_manual_polygon_layer(self, name: str | None) -> LayerSummary:
        if self.session is None:
            raise RuntimeError("数据库会话不可用。")
        project = await ProjectRepository(self.session).ensure_default_project()
        resolved_name = name or await self._next_manual_layer_name()
        layer = Layer(
            project_id=project.id,
            name=resolved_name,
            source_type="manual",
            geometry_type="Polygon",
            feature_count=0,
            crs="EPSG:3857",
            bounds={},
            style={"color": "#4656a8"},
            fields=[],
            performance={},
            visible=True,
            locked=False,
            opacity=1.0,
        )
        self.session.add(layer)
        try:
            await self.session.commit()
            await self.session.refresh(layer)
        except Exception:
            await self.session.rollback()
            raise
        return self.to_summary(layer)

    async def _next_manual_layer_name(self) -> str:
        if self.session is None:
            raise RuntimeError("数据库会话不可用。")
        prefix = "新建图斑图层 "
        names = (
            await self.session.scalars(select(Layer.name).where(Layer.name.startswith(prefix)))
        ).all()
        used_numbers = {
            int(name.removeprefix(prefix))
            for name in names
            if name.removeprefix(prefix).isdigit()
        }
        index = 1
        while index in used_numbers:
            index += 1
        return f"{prefix}{index}"

    @staticmethod
    def to_summary(layer: Layer, metadata: dict | None = None) -> LayerSummary:
        raw_metadata = metadata or layer.performance or {}
        source_format = layer.source_type or "unknown"
        container = LayerRepository._safe_provenance_path(
            raw_metadata.get("container") or layer.data_path,
            basename_only=True,
        )
        relative_path = LayerRepository._safe_provenance_path(
            raw_metadata.get("relative_path") or layer.data_path,
            basename_only=False,
        )
        return LayerSummary(
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
            performance=LayerPerformanceState.model_validate(raw_metadata),
            provenance=LayerProvenance(
                source_id=raw_metadata.get("source_id"),
                dataset_id=raw_metadata.get("dataset_id"),
                format=source_format,
                container=container,
                relative_path=relative_path,
                layer_name=raw_metadata.get("layer_name") or layer.name,
                fingerprint=raw_metadata.get("fingerprint"),
            ),
        )

    @staticmethod
    def _safe_provenance_path(value: object, *, basename_only: bool) -> str | None:
        if value in (None, ""):
            return None
        text = str(value).replace("\\", "/")
        windows_path = PureWindowsPath(str(value))
        if basename_only or Path(text).is_absolute() or windows_path.is_absolute():
            return windows_path.name or Path(text).name
        parts = [part for part in text.split("/") if part not in {"", ".", ".."}]
        return "/".join(parts) or None
