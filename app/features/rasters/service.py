from __future__ import annotations

import asyncio
import hashlib
import math
import re
import zipfile
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path
from uuid import uuid4

from app.features.jobs.execution import sanitize_job_error
from app.features.jobs.schemas import (
    JobStatus,
    RasterExportJobProgressDetail,
    RasterJobProgressDetail,
)
from app.features.layers.schemas import LayerSummary
from app.features.rasters.processor import RasterProcessor
from app.features.rasters.repository import RasterRepository
from app.features.rasters.schemas import (
    RasterCleanupResponse,
    RasterDeriveRequest,
    RasterExportRequest,
    RasterHistogramResponse,
    RasterPixelResponse,
    RasterStorageStatus,
    RasterStyle,
)
from app.features.rasters.storage import RasterStorage
from app.features.settings.service import SettingsService
from app.shared.config import ROOT_DIR
from app.shared.cache import JsonCache, get_performance_cache
from app.shared.database import AsyncSessionLocal
from app.shared.gdal import configure_bundled_gdal
from app.shared.runtime_performance import resolve_runtime_performance


configure_bundled_gdal()


class RasterService:
    def __init__(
        self,
        repository: RasterRepository,
        settings_service: SettingsService | None = None,
        cache: JsonCache | None = None,
    ) -> None:
        self.repository = repository
        self.settings_service = settings_service or SettingsService()
        self.cache = cache or get_performance_cache()

    async def storage(self) -> RasterStorage:
        settings = await self.settings_service.get_import_settings()
        return RasterStorage(
            settings.raster_store_path,
            settings.raster_scratch_path,
            settings.raster_quota_gb,
        )

    async def asset(self, layer_id: int, *, visible: bool = True) -> tuple[Path, str, str]:
        layer = await self.repository.require_raster_layer(layer_id, visible=visible)
        if not layer.data_path:
            raise KeyError(layer_id)
        storage = await self.storage()
        path = storage.assert_managed(layer.data_path)
        if not path.is_file():
            raise KeyError(layer_id)
        metadata = dict(layer.performance or {})
        fingerprint = str(metadata.get("fingerprint") or "")
        stat = path.stat()
        etag_value = fingerprint or hashlib.sha256(
            f"{layer.id}:{stat.st_size}:{stat.st_mtime_ns}".encode()
        ).hexdigest()
        etag = f'"{etag_value}"'
        last_modified = format_datetime(
            datetime.fromtimestamp(stat.st_mtime, UTC), usegmt=True
        )
        return path, etag, last_modified

    async def histogram(self, layer_id: int, band: int, bins: int) -> RasterHistogramResponse:
        path, etag, _ = await self.asset(layer_id, visible=False)
        asset_fingerprint = etag.strip('"')
        cache_key = f"raster-histogram/v1:{asset_fingerprint}:{band}:{bins}"
        cached = await self.cache.get(cache_key, RasterHistogramResponse)
        if cached.value is not None:
            return cached.value.model_copy(update={"cache_hit": True})
        response = await asyncio.to_thread(self._histogram, path, layer_id, band, bins)
        await self.cache.set(cache_key, response.model_copy(update={"cache_hit": False}))
        return response

    @staticmethod
    def _histogram(path: Path, layer_id: int, band: int, bins: int) -> RasterHistogramResponse:
        import numpy as np
        import rasterio

        with rasterio.open(path) as dataset:
            if band > dataset.count:
                raise ValueError("波段编号超出当前栅格范围。")
            scale = max(1.0, math.sqrt((dataset.width * dataset.height) / 262_144))
            width = max(1, int(dataset.width / scale))
            height = max(1, int(dataset.height / scale))
            values = dataset.read(band, out_shape=(height, width), masked=True)
            compressed = values.compressed().astype("float64")
            compressed = compressed[np.isfinite(compressed)]
            if compressed.size == 0:
                return RasterHistogramResponse(
                    layer_id=layer_id,
                    band=band,
                    bins=[],
                    edges=[],
                    minimum=None,
                    maximum=None,
                    percentiles={"p2": None, "p50": None, "p98": None},
                    sample_count=0,
                )
            counts, edges = np.histogram(compressed, bins=bins)
            percentiles = np.percentile(compressed, [2, 50, 98])
            return RasterHistogramResponse(
                layer_id=layer_id,
                band=band,
                bins=[int(value) for value in counts],
                edges=[float(value) for value in edges],
                minimum=float(compressed.min()),
                maximum=float(compressed.max()),
                percentiles={
                    "p2": float(percentiles[0]),
                    "p50": float(percentiles[1]),
                    "p98": float(percentiles[2]),
                },
                sample_count=int(compressed.size),
            )

    async def pixel(
        self, layer_id: int, x: float, y: float, crs: str
    ) -> RasterPixelResponse:
        path, _, _ = await self.asset(layer_id, visible=False)
        return await asyncio.to_thread(self._pixel, path, layer_id, x, y, crs)

    @staticmethod
    def _pixel(path: Path, layer_id: int, x: float, y: float, crs: str) -> RasterPixelResponse:
        import rasterio
        from rasterio.warp import transform

        with rasterio.open(path) as dataset:
            if dataset.crs is None:
                raise ValueError("托管栅格缺少 CRS。")
            target_x, target_y = x, y
            if crs != dataset.crs.to_string():
                transformed_x, transformed_y = transform(crs, dataset.crs, [x], [y])
                target_x, target_y = transformed_x[0], transformed_y[0]
            if not (
                dataset.bounds.left <= target_x <= dataset.bounds.right
                and dataset.bounds.bottom <= target_y <= dataset.bounds.top
            ):
                raise ValueError("查询坐标不在栅格范围内。")
            values = next(dataset.sample([(target_x, target_y)], masked=True))
            result = [
                None if bool(getattr(value, "mask", False)) else value.item()
                for value in values
            ]
            return RasterPixelResponse(
                layer_id=layer_id,
                x=x,
                y=y,
                crs=crs,
                values=result,
                nodata=all(value is None for value in result),
            )

    async def update_style(self, layer_id: int, style: RasterStyle) -> LayerSummary:
        layer = await self.repository.require_raster_layer(layer_id)
        band_count = int(((layer.performance or {}).get("raster") or {}).get("band_count") or 0)
        if any(band > band_count for band in style.bands):
            raise ValueError("样式引用的波段超出当前栅格范围。")
        if style.formula is not None:
            RasterProcessor.validate_formula(style.formula, band_count)
        return await self.repository.update_style(layer, style)

    async def queue_derive(self, layer_id: int, request: RasterDeriveRequest) -> JobStatus:
        layer = await self.repository.require_raster_layer(layer_id)
        band_count = int(((layer.performance or {}).get("raster") or {}).get("band_count") or 0)
        RasterProcessor.validate_formula(request.formula, band_count)
        return await self.repository.create_process_job(
            layer_id=layer_id,
            payload=request.model_dump(mode="json"),
        )

    async def queue_export(self, request: RasterExportRequest) -> JobStatus:
        await self.repository.raster_layers(request.layer_ids)
        return await self.repository.create_export_job(request.layer_ids, request.format)

    async def run_job(self, job_id: str) -> None:
        job = await self.repository.get_job(job_id)
        if job is None:
            return
        try:
            if job.job_type == "raster-derive":
                await self._run_derive(job)
            elif job.job_type == "raster-export":
                await self._run_export(job)
        except Exception as exc:
            await self.repository.session.rollback()
            raw = (job.result or {}).get("detail") or {}
            if job.job_type == "raster-export":
                detail = RasterExportJobProgressDetail.model_validate(raw)
            else:
                detail = RasterJobProgressDetail.model_validate(raw)
            detail.stage = "failed"
            detail.error = sanitize_job_error(exc)
            await self.repository.update_job(
                job,
                status="failed",
                message=f"栅格任务失败：{detail.error}",
                detail=detail,
            )

    async def _run_derive(self, job) -> None:
        payload = dict(job.payload or {})
        layer = await self.repository.require_raster_layer(int(payload["layer_id"]))
        if not layer.data_path:
            raise ValueError("源栅格资产不存在。")
        storage = await self.storage()
        processor = RasterProcessor(storage, resolve_runtime_performance())
        request = RasterDeriveRequest.model_validate(payload)
        fingerprint = hashlib.sha256(
            f"{(layer.performance or {}).get('fingerprint')}:{request.formula.model_dump_json()}".encode()
        ).hexdigest()
        detail = RasterJobProgressDetail(
            stage="processing",
            operation="derive",
            layer_id=layer.id,
            dataset_name=request.name,
        )
        await self.repository.update_job(
            job, status="running", progress=1, message="正在按块计算派生栅格。", detail=detail
        )

        def progress(stage: str, current: int, total: int) -> None:
            detail.stage = stage
            detail.processed_blocks = current
            detail.total_blocks = total

        result = await asyncio.to_thread(
            processor.materialize_formula,
            Path(layer.data_path),
            f"derived-{uuid4().hex[:16]}",
            fingerprint,
            request.formula,
            progress,
        )
        asset_path, metadata, bounds = result.path, result.metadata, result.bounds
        summary = await self.repository.create_derived_layer(
            name=request.name,
            asset_path=str(asset_path),
            metadata=metadata,
            bounds=bounds,
            fingerprint=fingerprint,
            source_layer_id=layer.id,
            style=request.style,
        )
        detail.stage = "completed"
        detail.layer_id = summary.id
        detail.phase_timings_ms = result.phase_timings.public_summary()
        detail.space_estimate_bytes = result.space_estimate.public_summary()
        await self.repository.update_job(
            job,
            status="done",
            progress=100,
            message="派生栅格已生成。",
            detail=detail,
            extra_result={"layer_id": summary.id},
        )

    async def _run_export(self, job) -> None:
        payload = dict(job.payload or {})
        layers = await self.repository.raster_layers([int(value) for value in payload["layer_ids"]])
        output_dir = ROOT_DIR / ".womap-data" / "raster-exports" / job.id
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"raster-export-{uuid4().hex[:16]}.zip"
        detail = RasterExportJobProgressDetail(stage="exporting", total_layers=len(layers))
        await self.repository.update_job(
            job, status="running", progress=1, message="正在打包栅格成果。", detail=detail
        )
        storage = await self.storage()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            for index, layer in enumerate(layers, start=1):
                if not layer.data_path:
                    raise ValueError(f"栅格图层 {layer.name} 缺少托管资产。")
                path = storage.assert_managed(layer.data_path)
                safe_name = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "-", layer.name).strip("-")
                archive.write(path, arcname=f"{safe_name[:80] or f'layer-{layer.id}'}.tif")
                detail.processed_layers = index
                await self.repository.update_job(
                    job,
                    progress=int(index / len(layers) * 95),
                    message=f"正在打包 {layer.name}",
                    detail=detail,
                )
        detail.stage = "completed"
        detail.artifact_name = output.name
        await self.repository.update_job(
            job,
            status="done",
            progress=100,
            message="栅格成果导出完成。",
            detail=detail,
            extra_result={"artifact_name": output.name},
        )

    async def export_path(self, job_id: str) -> tuple[Path, str]:
        job = await self.repository.get_job(job_id)
        if job is None or job.job_type != "raster-export" or job.status != "done":
            raise KeyError(job_id)
        filename = (job.result or {}).get("artifact_name")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise KeyError(job_id)
        root = (ROOT_DIR / ".womap-data" / "raster-exports" / job.id).resolve()
        path = (root / filename).resolve()
        if path.parent != root or not path.is_file():
            raise KeyError(job_id)
        return path, f"womap-raster-{job.id[-12:]}.zip"

    async def storage_status(self) -> RasterStorageStatus:
        storage = await self.storage()
        referenced = {
            storage.assert_managed(path) for path in await self.repository.referenced_asset_paths()
        }
        assets = storage.asset_paths()
        used = storage.usage_bytes()
        return RasterStorageStatus(
            used_bytes=used,
            quota_bytes=storage.quota_bytes,
            available_bytes=max(0, storage.quota_bytes - used),
            managed_assets=len(assets),
            orphan_assets=len(assets - referenced),
            scratch_bytes=storage.scratch_bytes(),
            store_path=storage.display_path(storage.root),
            scratch_path=storage.display_path(storage.scratch),
        )

    async def cleanup(self) -> RasterCleanupResponse:
        storage = await self.storage()
        referenced = {
            storage.assert_managed(path) for path in await self.repository.referenced_asset_paths()
        }
        deleted, freed = await asyncio.to_thread(storage.cleanup_orphans, referenced)
        return RasterCleanupResponse(deleted_assets=deleted, freed_bytes=freed)


async def execute_raster_job(job_id: str, session_factory=AsyncSessionLocal) -> None:
    async with session_factory() as session:
        await RasterService(RasterRepository(session)).run_job(job_id)
