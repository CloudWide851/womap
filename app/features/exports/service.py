from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from uuid import uuid4

from app.features.exports.repository import ExportRepository
from app.features.exports.schemas import ExportFormat
from app.features.exports.writer import ExportArchive, ExportDependencyError, GdalVectorWriter
from app.features.jobs.execution import sanitize_job_error
from app.features.jobs.schemas import JobStatus, VectorExportJobProgressDetail
from app.shared.config import ROOT_DIR
from app.shared.database import AsyncSessionLocal


VECTOR_EXPORT_ROOT = ROOT_DIR / ".womap-data" / "vector-exports"


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

        raster_ids = await self.repository.raster_layer_ids(normalized_ids)
        if raster_ids:
            raise ExportRequestError("SHP/GDB 仅支持矢量图层；请从栅格导出入口导出 COG。")

        layers = await self.repository.list_layers_for_export(normalized_ids)
        if not layers:
            raise ExportNoDataError("没有找到可导出的后端图层或图斑。")

        return self.writer.write(export_format, layers)

    async def queue_export(self, export_format: ExportFormat, layer_ids: list[int]) -> JobStatus:
        normalized_ids = self._normalize_layer_ids(layer_ids)
        if not normalized_ids:
            raise ExportRequestError("请至少选择一个后端图层。")
        try:
            await self.repository.validate_export_layers(normalized_ids)
        except ValueError as exc:
            raise ExportRequestError(str(exc)) from exc
        except LookupError as exc:
            raise ExportNoDataError(str(exc)) from exc
        return await self.repository.create_job(export_format, normalized_ids)

    async def run_job(self, job_id: str) -> None:
        job = await self.repository.get_job(job_id)
        if job is None or job.job_type != "vector-export":
            return
        detail = VectorExportJobProgressDetail.model_validate(
            (job.result or {}).get("detail") or {}
        )
        try:
            payload = dict(job.payload or {})
            layer_ids = [int(value) for value in payload.get("layer_ids") or []]
            export_format: ExportFormat = payload["format"]
            detail.stage = "exporting"
            await self.repository.update_job(
                job,
                status="running",
                progress=2,
                message="正在读取矢量图层并生成成果。",
                detail=detail,
            )
            layers = await self.repository.list_layers_for_export(layer_ids)
            if not layers:
                raise ExportNoDataError("没有找到可导出的后端图层或图斑。")
            archive = await asyncio.to_thread(self.writer.write, export_format, layers)
            output_dir = VECTOR_EXPORT_ROOT / job.id
            output_dir.mkdir(parents=True, exist_ok=True)
            destination = output_dir / f"vector-export-{uuid4().hex[:16]}.zip"
            temporary = output_dir / f".{destination.name}.part"
            try:
                temporary.unlink(missing_ok=True)
                shutil.move(str(archive.path), temporary)
                temporary.replace(destination)
            finally:
                shutil.rmtree(archive.cleanup_path, ignore_errors=True)
            detail.stage = "completed"
            detail.processed_layers = len(layers)
            detail.total_layers = len(layers)
            detail.artifact_name = destination.name
            await self.repository.update_job(
                job,
                status="done",
                progress=100,
                message="矢量成果导出完成。",
                detail=detail,
                extra_result={"artifact_name": destination.name, "download_ready": True},
            )
        except Exception as exc:
            await self.repository.rollback()
            detail.stage = "failed"
            detail.error = sanitize_job_error(exc)
            await self.repository.update_job(
                job,
                status="failed",
                message=f"矢量成果导出失败：{detail.error}",
                detail=detail,
            )

    async def download_path(self, job_id: str) -> tuple[Path, str]:
        job = await self.repository.get_job(job_id)
        if job is None or job.job_type != "vector-export" or job.status != "done":
            raise KeyError(job_id)
        filename = (job.result or {}).get("artifact_name")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise KeyError(job_id)
        root = (VECTOR_EXPORT_ROOT / job.id).resolve()
        path = (root / filename).resolve()
        if path.parent != root or not path.is_file():
            raise KeyError(job_id)
        format_name = str((job.payload or {}).get("format") or "shp")
        return path, f"womap-export-{format_name}-{job.id[-12:]}.zip"

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


async def execute_vector_export_job(job_id: str, session_factory=AsyncSessionLocal) -> None:
    async with session_factory() as session:
        await ExportService(repository=ExportRepository(session=session)).run_job(job_id)
