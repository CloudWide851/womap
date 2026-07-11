from __future__ import annotations

import asyncio
import math
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from geoalchemy2.shape import from_shape
from pyproj import Transformer

from app.features.imports.repository import ImportRepository
from app.features.imports.scanner import VectorDatasetScanner
from app.features.imports.schemas import CatalogDataset, ImportCatalog, ImportRequest
from app.features.imports.sources import SourceMaterializer, TransferProgress
from app.features.jobs.repository import JobRepository
from app.features.jobs.schemas import JobProgressDetail, JobStatus
from app.features.settings.schemas import ImportSourceResponse
from app.features.settings.service import SettingsService
from app.models.job import Job
from app.shared.config import ROOT_DIR
from app.shared.database import AsyncSessionLocal


class ImportService:
    def __init__(
        self,
        repository: ImportRepository,
        settings_service: SettingsService | None = None,
        scanner: VectorDatasetScanner | None = None,
        materializer: SourceMaterializer | None = None,
    ) -> None:
        self.repository = repository
        self.settings_service = settings_service or SettingsService()
        self.scanner = scanner or VectorDatasetScanner()
        self.materializer = materializer or SourceMaterializer(
            self.settings_service.credential_store
        )

    async def queue_sync(self, source_id: str) -> JobStatus:
        await self._source(source_id)
        return await self.repository.create_job("import-sync", source_id, {})

    async def queue_import(self, request: ImportRequest) -> JobStatus:
        catalog = await self.get_catalog(request.source_id)
        selected = [item for item in catalog.datasets if item.id in request.dataset_ids]
        if len(selected) != len(set(request.dataset_ids)):
            raise ValueError("所选数据集中包含不存在的目录项，请先重新同步。")
        invalid = [item.layer_name for item in selected if not item.valid]
        if invalid:
            raise ValueError(f"以下数据未通过完整性校验：{', '.join(invalid)}")
        missing_crs = [
            item.layer_name
            for item in selected
            if not item.crs and not request.crs_overrides.get(item.id)
        ]
        if missing_crs:
            raise ValueError(f"以下数据缺少坐标系，请指定 EPSG：{', '.join(missing_crs)}")
        return await self.repository.create_job(
            "import-data",
            request.source_id,
            {
                "dataset_ids": request.dataset_ids,
                "crs_overrides": request.crs_overrides,
            },
        )

    async def resume(self, job_id: str) -> JobStatus:
        job = await self.repository.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if job.job_type not in {"import-sync", "import-data"}:
            raise ValueError("该任务不支持导入恢复。")
        if job.status not in {"interrupted", "failed"}:
            raise ValueError("只有中断或失败的任务可以继续。")
        source_id = str((job.payload or {}).get("source_id", ""))
        if await self.repository.has_active_job(source_id):
            raise RuntimeError("该数据源已有任务正在执行。")
        detail = JobProgressDetail.model_validate((job.result or {}).get("detail") or {})
        detail.stage = "queued"
        detail.error = None
        await self.repository.update_job(
            job,
            status="queued",
            message="任务已重新进入队列。",
            detail=detail,
        )
        return JobRepository.to_status(job)

    async def get_catalog(self, source_id: str) -> ImportCatalog:
        await self._source(source_id)
        catalog = self._load_catalog(source_id)
        imported_layers = await self.repository.imported_layers(source_id)
        layer_by_dataset = {
            str((layer.performance or {}).get("dataset_id")): layer for layer in imported_layers
        }
        for dataset in catalog.datasets:
            layer = layer_by_dataset.get(dataset.id)
            if layer is not None:
                old_fingerprint = str((layer.performance or {}).get("fingerprint", ""))
                dataset.import_state = (
                    "imported" if old_fingerprint == dataset.fingerprint else "changed"
                )
            resumable = await self.repository.find_resumable_job(source_id, dataset.id)
            if resumable is not None:
                dataset.import_state = "interrupted"
                dataset.resumable_job_id = resumable.id
        return catalog

    async def run_job(self, job_id: str) -> None:
        job = await self.repository.get_job(job_id)
        if job is None:
            return
        try:
            if job.job_type == "import-sync":
                await self._run_sync(job)
            elif job.job_type == "import-data":
                await self._run_import(job)
        except asyncio.CancelledError:
            await self.repository.rollback()
            detail = JobProgressDetail.model_validate((job.result or {}).get("detail") or {})
            detail.stage = "interrupted"
            await self.repository.update_job(
                job,
                status="interrupted",
                message="任务已中断，可稍后继续。",
                detail=detail,
            )
            raise
        except Exception as exc:
            await self.repository.rollback()
            detail = JobProgressDetail.model_validate((job.result or {}).get("detail") or {})
            detail.stage = "failed"
            detail.error = str(exc)
            await self.repository.update_job(
                job,
                status="failed",
                message=f"任务失败：{exc}",
                detail=detail,
            )

    async def _run_sync(self, job: Job) -> None:
        source_id = str(job.payload["source_id"])
        source = await self._source(source_id)
        import_settings = await self.settings_service.get_import_settings()
        cache_root = self._resolve_local_path(import_settings.cache_path)
        detail = JobProgressDetail(stage="scanning", source_id=source_id)
        await self.repository.update_job(
            job, status="running", progress=1, message="正在扫描数据源。", detail=detail
        )

        transfer = TransferProgress()
        materialize_task = asyncio.create_task(
            asyncio.to_thread(self.materializer.materialize, source, cache_root, transfer)
        )
        while not materialize_task.done():
            copied, total, current = transfer.snapshot()
            if total:
                detail.stage = "transferring"
                detail.transferred_bytes = copied
                detail.total_bytes = total
                detail.current_file = current or None
                await self.repository.update_job(
                    job,
                    progress=min(35, int(copied / total * 35)),
                    message=f"正在同步 {current or source.name}",
                    detail=detail,
                )
            await asyncio.sleep(0.25)
        root = await materialize_task

        detail.stage = "scanning"
        await self.repository.update_job(
            job, progress=40, message="正在识别 SHP 和 GDB 图层。", detail=detail
        )
        catalog = await asyncio.to_thread(self.scanner.scan, source_id, root)
        self._save_catalog(catalog)
        detail.stage = "completed"
        detail.current_file = None
        await self.repository.update_job(
            job,
            status="done",
            progress=100,
            message=f"同步完成，共发现 {len(catalog.datasets)} 个空间数据集。",
            detail=detail,
            extra_result={"dataset_count": len(catalog.datasets)},
        )

    async def _run_import(self, job: Job) -> None:
        source_id = str(job.payload["source_id"])
        source = await self._source(source_id)
        import_settings = await self.settings_service.get_import_settings()
        cache_root = self._resolve_local_path(import_settings.cache_path)
        root = await asyncio.to_thread(self.materializer.materialize, source, cache_root, None)
        catalog = self._load_catalog(source_id)
        selected_ids = list(job.payload.get("dataset_ids", []))
        selected = [dataset for dataset in catalog.datasets if dataset.id in selected_ids]
        overrides = dict(job.payload.get("crs_overrides", {}))
        total_features = sum(dataset.feature_count for dataset in selected)
        state = dict(job.result or {})
        offsets = dict(state.get("offsets") or {})
        staging_layers = dict(state.get("staging_layers") or {})
        completed = set(state.get("completed_dataset_ids") or [])
        imported_before = sum(
            dataset.feature_count for dataset in selected if dataset.id in completed
        )

        for dataset in selected:
            if dataset.id in completed:
                continue
            path = self._dataset_path(root, dataset)
            source_crs = dataset.crs or overrides.get(dataset.id)
            if not source_crs:
                raise ValueError(f"{dataset.layer_name} 缺少坐标系。")
            layer_id = staging_layers.get(dataset.id)
            layer = await self.repository.get_layer(int(layer_id)) if layer_id else None
            if layer is None:
                layer = await self.repository.create_staging_layer(dataset, job.id)
                staging_layers[dataset.id] = layer.id
            offset = int(offsets.get(dataset.id, 0))
            total_batches = max(1, math.ceil(dataset.feature_count / import_settings.batch_size))

            while offset < dataset.feature_count:
                dataframe = await asyncio.to_thread(
                    self._read_batch,
                    path,
                    dataset,
                    offset,
                    import_settings.batch_size,
                    source_crs,
                )
                if dataframe.empty:
                    break
                rows = self._feature_rows(dataframe, dataset)
                next_offset = offset + len(dataframe)
                offsets[dataset.id] = next_offset
                detail = JobProgressDetail(
                    stage="importing",
                    source_id=source_id,
                    dataset_id=dataset.id,
                    dataset_name=dataset.layer_name,
                    current_layer=dataset.layer_name,
                    imported_features=imported_before + next_offset,
                    total_features=total_features,
                    current_batch=math.ceil(next_offset / import_settings.batch_size),
                    total_batches=total_batches,
                    warnings=[
                        f"缺少可选附件 {', '.join(dataset.missing_optional)}"
                    ]
                    if dataset.missing_optional
                    else [],
                )
                await self.repository.insert_batch(
                    layer,
                    job,
                    rows,
                    detail,
                    {
                        "offsets": offsets,
                        "staging_layers": staging_layers,
                        "completed_dataset_ids": list(completed),
                    },
                )
                offset = next_offset

            layer.bounds = self._bounds_3857(dataset.bounds, source_crs)
            await self.repository.finalize_layer(layer, dataset)
            completed.add(dataset.id)
            imported_before += dataset.feature_count
            await self.repository.update_job(
                job,
                progress=int(imported_before / max(1, total_features) * 100),
                message=f"已完成 {dataset.layer_name}",
                detail=JobProgressDetail(
                    stage="finalizing",
                    source_id=source_id,
                    dataset_id=dataset.id,
                    dataset_name=dataset.layer_name,
                    current_layer=dataset.layer_name,
                    imported_features=imported_before,
                    total_features=total_features,
                    current_batch=total_batches,
                    total_batches=total_batches,
                ),
                extra_result={
                    "offsets": offsets,
                    "staging_layers": staging_layers,
                    "completed_dataset_ids": list(completed),
                },
            )

        await self.repository.update_job(
            job,
            status="done",
            progress=100,
            message=f"导入完成，共处理 {len(completed)} 个图层。",
            detail=JobProgressDetail(
                stage="completed",
                source_id=source_id,
                imported_features=total_features,
                total_features=total_features,
            ),
            extra_result={
                "offsets": offsets,
                "staging_layers": staging_layers,
                "completed_dataset_ids": list(completed),
            },
        )

    @staticmethod
    def _read_batch(
        path: Path,
        dataset: CatalogDataset,
        offset: int,
        batch_size: int,
        source_crs: str,
    ):
        import pyogrio

        dataframe = pyogrio.read_dataframe(
            path,
            layer=dataset.layer_name if dataset.format == "gdb" else None,
            skip_features=offset,
            max_features=batch_size,
            fid_as_index=True,
            on_invalid="warn",
        )
        if dataframe.crs is None:
            dataframe = dataframe.set_crs(source_crs)
        return dataframe.to_crs("EPSG:3857")

    @classmethod
    def _feature_rows(cls, dataframe, dataset: CatalogDataset) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        geometry_name = dataframe.geometry.name
        for feature_id, record in dataframe.iterrows():
            geometry = record[geometry_name]
            if geometry is None or geometry.is_empty:
                continue
            properties = {
                str(name): cls._json_value(value)
                for name, value in record.items()
                if name != geometry_name
            }
            min_x, min_y, max_x, max_y = geometry.bounds
            rows.append(
                {
                    "source_feature_id": f"{dataset.id}:{feature_id}",
                    "geom": from_shape(geometry, srid=3857),
                    "properties": properties,
                    "bbox": {
                        "min_x": min_x,
                        "min_y": min_y,
                        "max_x": max_x,
                        "max_y": max_y,
                    },
                    "area": float(geometry.area) if geometry.geom_type.endswith("Polygon") else None,
                    "perimeter": float(geometry.length),
                    "revision": 1,
                }
            )
        return rows

    @staticmethod
    def _json_value(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        try:
            if bool(value != value):
                return None
        except (TypeError, ValueError):
            pass
        if hasattr(value, "item"):
            value = value.item()
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    @staticmethod
    def _bounds_3857(bounds: list[float], source_crs: str) -> dict[str, float]:
        if len(bounds) != 4:
            return {}
        transformer = Transformer.from_crs(source_crs, "EPSG:3857", always_xy=True)
        min_x, min_y = transformer.transform(bounds[0], bounds[1])
        max_x, max_y = transformer.transform(bounds[2], bounds[3])
        return {"min_x": min_x, "min_y": min_y, "max_x": max_x, "max_y": max_y}

    async def _source(self, source_id: str) -> ImportSourceResponse:
        settings = await self.settings_service.get_import_settings()
        source = next((item for item in settings.sources if item.id == source_id), None)
        if source is None or not source.enabled:
            raise KeyError(source_id)
        return source

    @staticmethod
    def _resolve_local_path(value: str) -> Path:
        path = Path(value).expanduser()
        return path.resolve() if path.is_absolute() else (ROOT_DIR / path).resolve()

    def _catalog_path(self, source_id: str) -> Path:
        return ROOT_DIR / ".womap-data" / "catalog" / f"{source_id}.json"

    def _save_catalog(self, catalog: ImportCatalog) -> None:
        path = self._catalog_path(catalog.source_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(catalog.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(path)

    def _load_catalog(self, source_id: str) -> ImportCatalog:
        path = self._catalog_path(source_id)
        if not path.exists():
            return ImportCatalog(
                source_id=source_id,
                scanned_at=datetime.now(UTC).isoformat(),
            )
        return ImportCatalog.model_validate_json(path.read_text(encoding="utf-8"))

    @staticmethod
    def _dataset_path(root: Path, dataset: CatalogDataset) -> Path:
        path = (root / Path(dataset.relative_path)).resolve()
        if root.resolve() not in path.parents:
            raise ValueError("数据集路径超出配置的数据源根目录。")
        return path


async def execute_import_job(job_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await ImportService(ImportRepository(session)).run_job(job_id)
