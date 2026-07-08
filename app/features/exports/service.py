from __future__ import annotations

from app.features.exports.repository import ExportRepository
from app.features.exports.schemas import ExportFormat
from app.features.exports.writer import ExportArchive, ExportDependencyError, GdalVectorWriter


class ExportRequestError(Exception):
    pass


class ExportNoDataError(Exception):
    pass


class ExportService:
    def __init__(
        self,
        repository: ExportRepository | None = None,
        writer: GdalVectorWriter | None = None,
    ) -> None:
        self.repository = repository or ExportRepository()
        self.writer = writer or GdalVectorWriter()

    async def export_layers(self, export_format: ExportFormat, layer_ids: list[int]) -> ExportArchive:
        normalized_ids = self._normalize_layer_ids(layer_ids)
        if not normalized_ids:
            raise ExportRequestError("请至少选择一个后端图层。")

        layers = await self.repository.list_layers_for_export(normalized_ids)
        if not layers:
            raise ExportNoDataError("没有找到可导出的后端图层或图斑。")

        return self.writer.write(export_format, layers)

    def _normalize_layer_ids(self, layer_ids: list[int]) -> list[int]:
        normalized: list[int] = []
        seen: set[int] = set()
        for layer_id in layer_ids:
            if layer_id <= 0 or layer_id in seen:
                continue
            seen.add(layer_id)
            normalized.append(layer_id)
        return normalized


__all__ = [
    "ExportDependencyError",
    "ExportNoDataError",
    "ExportRequestError",
    "ExportService",
]
