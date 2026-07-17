from __future__ import annotations

import asyncio
import hashlib
import shutil
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import UploadFile
from geoalchemy2.shape import from_shape

from app.features.jobs.execution import sanitize_job_error
from app.features.jobs.repository import JobRepository
from app.features.jobs.schemas import JobStatus, WorkspacePackageJobProgressDetail
from app.features.projects.repository import ProjectRepository
from app.features.rasters.processor import RasterProcessor
from app.features.rasters.storage import RasterStorage
from app.features.workspaces.package_io import (
    MAX_COMPRESSED_BYTES,
    WorkspacePackageError,
    build_workspace_package,
    extract_geopackage,
    extract_raster_assets,
    read_package_layer,
    validate_workspace_package,
)
from app.features.workspaces.package_repository import WorkspacePackageRepository
from app.features.workspaces.repository import WorkspaceRepository
from app.features.workspaces.schemas import (
    WorkspaceBasemapReference,
    WorkspaceDefinition,
    WorkspaceFeatureSelection,
    WorkspaceLayerConfig,
    WorkspacePackageImportRequest,
    WorkspacePackagePreview,
)
from app.features.workspaces.service import WorkspaceService
from app.models.layer import Layer
from app.models.map_feature import MapFeature
from app.models.project import Project
from app.shared.config import ROOT_DIR, get_settings
from app.shared.database import AsyncSessionLocal

PACKAGE_ROOT = ROOT_DIR / ".womap-data" / "workspace-packages"
UPLOAD_ROOT = PACKAGE_ROOT / "uploads"
ARTIFACT_ROOT = PACKAGE_ROOT / "artifacts"


class WorkspacePackageConflictError(RuntimeError):
    pass


class WorkspacePackageService:
    def __init__(
        self,
        repository: WorkspacePackageRepository,
        workspace_service: WorkspaceService,
    ) -> None:
        self.repository = repository
        self.workspace_service = workspace_service
        self.settings = get_settings()

    async def queue_export(self, workspace_id: int, *, include_rasters: bool = False) -> JobStatus:
        await self.workspace_service.get_workspace(workspace_id)
        return await self.repository.create_job(
            job_type="workspace-export",
            workspace_id=workspace_id,
            operation="export",
            payload={"include_rasters": include_rasters},
        )

    async def save_and_preview(self, upload: UploadFile) -> WorkspacePackagePreview:
        filename = upload.filename or ""
        if not filename.lower().endswith(".womap.zip"):
            raise WorkspacePackageError("请选择扩展名为 .womap.zip 的工作空间包。")
        UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
        token = uuid4().hex
        target = UPLOAD_ROOT / f"{token}.womap.zip"
        written = 0
        try:
            with target.open("wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    written += len(chunk)
                    if written > MAX_COMPRESSED_BYTES:
                        raise WorkspacePackageError("工作空间包压缩体积超过 2 GiB。")
                    output.write(chunk)
            package = await asyncio.to_thread(validate_workspace_package, target)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        manifest = package.manifest
        conflict = await self.repository.find_workspace_by_uuid(manifest.workspace_uuid)
        provider_ids = {provider.id for provider in self.settings.maps.enabled_providers}
        basemap_missing = manifest.basemap.id not in provider_ids
        warnings = ["本机缺少包内底图，导入后将回退到默认底图。"] if basemap_missing else []
        referenced_rasters = sum(
            layer.kind == "raster" and layer.asset_member is None for layer in manifest.layers
        )
        if referenced_rasters:
            warnings.append(
                f"包内有 {referenced_rasters} 个栅格仅保存引用；本机无匹配数据时将跳过。"
            )
        return WorkspacePackagePreview(
            upload_token=token,
            workspace_name=manifest.workspace_name,
            workspace_uuid=manifest.workspace_uuid,
            revision=manifest.revision,
            package_version=manifest.package_format,
            layer_count=len(manifest.layers),
            feature_count=sum(layer.feature_count for layer in manifest.layers),
            basemap=manifest.basemap,
            basemap_missing=basemap_missing,
            conflicting_workspace_id=conflict.id if conflict else None,
            warnings=warnings,
        )

    async def queue_import(self, payload: WorkspacePackageImportRequest) -> JobStatus:
        upload_path = self._upload_path(payload.upload_token)
        package = await asyncio.to_thread(validate_workspace_package, upload_path)
        conflict = await self.repository.find_workspace_by_uuid(package.manifest.workspace_uuid)
        target_id = payload.target_workspace_id
        if payload.strategy == "replace":
            if conflict is None:
                raise WorkspacePackageConflictError("没有找到相同 UUID 的工作空间，无法覆盖。")
            if target_id is not None and target_id != conflict.id:
                raise WorkspacePackageConflictError("覆盖目标与工作空间包 UUID 不一致。")
            target_id = conflict.id
        return await self.repository.create_job(
            job_type="workspace-import",
            workspace_id=target_id,
            operation="import",
            payload={
                "upload_token": payload.upload_token,
                "strategy": payload.strategy,
                "target_workspace_id": target_id,
            },
        )

    async def run_job(self, job_id: str) -> None:
        job = await self.repository.get_job(job_id)
        if job is None:
            return
        detail = WorkspacePackageJobProgressDetail.model_validate(
            (job.result or {}).get("detail") or {}
        )
        try:
            detail.stage = "running"
            await self.repository.update_job(
                job,
                status="running",
                progress=2,
                message="正在处理工作空间包。",
                detail=detail,
            )
            if job.job_type == "workspace-export":
                await self._run_export(job, detail)
            elif job.job_type == "workspace-import":
                await self._run_import(job, detail)
            else:
                raise WorkspacePackageError("未知的工作空间包任务类型。")
        except asyncio.CancelledError:
            await self.repository.rollback()
            detail.stage = "interrupted"
            detail.error = "任务已中断。"
            await self.repository.update_job(
                job,
                status="interrupted",
                message="工作空间包任务已中断。",
                detail=detail,
            )
            raise
        except Exception as exc:
            await self.repository.rollback()
            detail.stage = "failed"
            detail.error = sanitize_job_error(exc)
            await self.repository.update_job(
                job,
                status="failed",
                message=f"工作空间包任务失败：{detail.error}",
                detail=detail,
            )

    async def _run_export(self, job, detail: WorkspacePackageJobProgressDetail) -> None:
        workspace_id = int(job.payload["workspace_id"])
        workspace = await self.workspace_service.get_workspace(workspace_id)
        detail.workspace_id = workspace_id
        detail.total_features = sum(state.layer.feature_count for state in workspace.layers)
        layer_features: dict[int, list[dict]] = {}
        raster_assets: dict[int, Path] = {}
        include_rasters = bool((job.payload or {}).get("include_rasters"))
        storage = None
        if include_rasters:
            storage = RasterStorage(
                self.settings.imports.raster_store_path,
                self.settings.imports.raster_scratch_path,
                self.settings.imports.raster_quota_gb,
            )
        processed = 0
        for state in workspace.layers:
            detail.current_layer = state.layer.name
            if state.layer.kind == "raster":
                layer_features[state.layer.id] = []
                raster_layer = await self.repository.get_layer(state.layer.id)
                if (
                    include_rasters
                    and raster_layer is not None
                    and raster_layer.data_path
                    and storage is not None
                ):
                    try:
                        raster_assets[state.layer.id] = storage.assert_managed(
                            raster_layer.data_path
                        )
                    except ValueError:
                        detail.warnings.append(
                            f"栅格 {state.layer.name} 不在托管目录，工作空间包仅保留引用。"
                        )
                elif not include_rasters:
                    detail.warnings.append(
                        f"栅格 {state.layer.name} 未内嵌，工作空间包仅保留引用。"
                    )
                continue
            rows = await self.repository.list_feature_rows(state.layer.id, state.config.selection)
            layer_features[state.layer.id] = rows
            processed += len(rows)
            detail.processed_features = processed
        provider = next(
            (item for item in self.settings.maps.enabled_providers if item.id == workspace.default_basemap),
            None,
        )
        basemap = WorkspaceBasemapReference(
            id=workspace.default_basemap,
            name=provider.name if provider else workspace.default_basemap,
            type=provider.type if provider else "xyz",
        )
        output_dir = ARTIFACT_ROOT / job.id
        output_dir.mkdir(parents=True, exist_ok=True)
        execution_id = uuid4().hex[:16]
        work_dir = output_dir / f".work-{execution_id}"
        try:
            archive = await asyncio.to_thread(
                build_workspace_package,
                output_dir=work_dir,
                workspace=workspace,
                basemap=basemap,
                layer_features=layer_features,
                raster_assets=raster_assets,
            )
            stem = archive.filename.removesuffix(".womap.zip")
            artifact_name = f"{stem}-{execution_id}.womap.zip"
            archive.path.replace(output_dir / artifact_name)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
        detail.stage = "done"
        detail.current_layer = None
        detail.processed_features = sum(len(rows) for rows in layer_features.values())
        detail.total_features = detail.processed_features
        detail.artifact_name = artifact_name
        await self.repository.update_job(
            job,
            status="done",
            progress=100,
            message="工作空间包已生成。",
            detail=detail,
            extra_result={"artifact_name": artifact_name, "download_ready": True},
        )

    async def _run_import(self, job, detail: WorkspacePackageJobProgressDetail) -> None:
        token = str(job.payload["upload_token"])
        package = await asyncio.to_thread(validate_workspace_package, self._upload_path(token))
        manifest = package.manifest
        detail.total_features = sum(layer.feature_count for layer in manifest.layers)
        extract_dir = PACKAGE_ROOT / "work" / job.id
        shutil.rmtree(extract_dir, ignore_errors=True)
        try:
            gpkg_path = await asyncio.to_thread(extract_geopackage, package, extract_dir)
            raster_assets = await asyncio.to_thread(
                extract_raster_assets, package, extract_dir / "rasters"
            )
            layer_rows = {}
            for layer_manifest in manifest.layers:
                detail.current_layer = layer_manifest.name
                layer_rows[layer_manifest.package_layer] = (
                    []
                    if layer_manifest.kind == "raster"
                    else await asyncio.to_thread(
                        read_package_layer,
                        gpkg_path,
                        layer_manifest,
                    )
                )
            imported, warnings = await self._persist_import(
                job, manifest, layer_rows, raster_assets
            )
            detail.warnings.extend(warnings)
        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)
        detail.workspace_id = imported.id
        detail.stage = "done"
        detail.current_layer = None
        detail.processed_features = detail.total_features
        await self.repository.update_job(
            job,
            status="done",
            progress=100,
            message="工作空间包已导入。",
            detail=detail,
            extra_result={"workspace_id": imported.id, "workspace_name": imported.name},
        )
        self._upload_path(token).unlink(missing_ok=True)

    async def _persist_import(
        self,
        job,
        manifest,
        layer_rows: dict[str, list[dict]],
        raster_assets: dict[str, Path],
    ) -> tuple[Project, list[str]]:
        strategy: Literal["copy", "replace"] = job.payload.get("strategy", "copy")
        workspace_repository = WorkspaceRepository(self.repository.session)
        default_project = await ProjectRepository(self.repository.session).ensure_default_project()
        await self.repository.session.commit()
        target: Project | None = None
        if strategy == "replace":
            target_id = int(job.payload["target_workspace_id"])
            target = await workspace_repository.get_project(target_id)
            if target is None or str((target.current_view or {}).get("workspace_uuid")) != manifest.workspace_uuid:
                raise WorkspacePackageConflictError("覆盖目标已变化，请重新预览工作空间包。")
            workspace_uuid = manifest.workspace_uuid
            workspace_name = target.name
            revision = int((target.current_view or {}).get("revision") or 1) + 1
        else:
            workspace_uuid = str(uuid4())
            workspace_name = await self._copy_name(manifest.workspace_name, workspace_repository)
            revision = 1
        imported_configs: list[WorkspaceLayerConfig] = []
        warnings: list[str] = []
        installed_assets: list[Path] = []
        existing_layers = await workspace_repository.list_layers()
        existing_by_dataset = {
            str((layer.performance or {}).get("dataset_id")): layer
            for layer in existing_layers
            if (layer.performance or {}).get("dataset_id")
        }
        try:
            for layer_manifest in manifest.layers:
                rows = layer_rows[layer_manifest.package_layer]
                dataset_id = f"workspace:{workspace_uuid}:{layer_manifest.package_layer}"
                if layer_manifest.kind == "raster":
                    embedded = raster_assets.get(layer_manifest.package_layer)
                    if embedded is None:
                        existing = existing_by_dataset.get(str(layer_manifest.dataset_id))
                        existing_fingerprint = str(
                            (existing.performance or {}).get("fingerprint") if existing else ""
                        )
                        if (
                            existing is None
                            or existing.geometry_type != "Raster"
                            or not existing.data_path
                            or (
                                layer_manifest.fingerprint
                                and existing_fingerprint != layer_manifest.fingerprint
                            )
                        ):
                            warnings.append(
                                f"栅格 {layer_manifest.name} 未内嵌且本机无匹配资产，已跳过。"
                            )
                            continue
                        imported_configs.append(
                            WorkspaceLayerConfig(
                                layer_id=existing.id,
                                dataset_id=str(layer_manifest.dataset_id),
                                visible=layer_manifest.config.visible,
                                opacity=layer_manifest.config.opacity,
                                order=len(imported_configs),
                                selection=WorkspaceFeatureSelection(mode="all"),
                                raster_style=layer_manifest.config.raster_style,
                            )
                        )
                        continue
                    asset_path, raster_metadata, bounds = await asyncio.to_thread(
                        self._install_raster_asset,
                        embedded,
                        layer_manifest.fingerprint,
                    )
                    installed_assets.append(asset_path)
                    raster_style = (
                        layer_manifest.config.raster_style.model_dump(mode="json")
                        if layer_manifest.config.raster_style
                        else {
                            "schema_version": "womap.raster-style/v1",
                            "mode": "rgb" if raster_metadata.get("band_count", 0) >= 3 else "grayscale",
                            "bands": [1, 2, 3]
                            if raster_metadata.get("band_count", 0) >= 3
                            else [1],
                            "stretch": "percentile",
                            "gamma": 1.0,
                            "nodata_transparent": True,
                        }
                    )
                    layer = Layer(
                        project_id=default_project.id,
                        name=layer_manifest.name,
                        source_type="workspace-raster",
                        geometry_type="Raster",
                        feature_count=0,
                        crs="EPSG:3857",
                        bounds=bounds,
                        style={"raster": raster_style},
                        fields=[],
                        performance={
                            "source_id": f"workspace-package:{workspace_uuid}",
                            "dataset_id": dataset_id,
                            "container": f"{workspace_name}.womap.zip",
                            "layer_name": layer_manifest.name,
                            "fingerprint": layer_manifest.fingerprint,
                            "raster": raster_metadata,
                            "staging": False,
                            "import_job_id": job.id,
                        },
                        data_path=str(asset_path),
                        visible=layer_manifest.config.visible,
                        locked=True,
                        opacity=layer_manifest.config.opacity,
                    )
                    self.repository.session.add(layer)
                    await self.repository.session.flush()
                    imported_configs.append(
                        WorkspaceLayerConfig(
                            layer_id=layer.id,
                            dataset_id=dataset_id,
                            visible=layer_manifest.config.visible,
                            opacity=layer_manifest.config.opacity,
                            order=len(imported_configs),
                            selection=WorkspaceFeatureSelection(mode="all"),
                            raster_style=layer_manifest.config.raster_style,
                        )
                    )
                    continue
                layer = Layer(
                    project_id=default_project.id,
                    name=layer_manifest.name,
                    source_type="workspace",
                    geometry_type=layer_manifest.geometry_type,
                    feature_count=len(rows),
                    crs="EPSG:3857",
                    bounds=self._rows_bounds(rows),
                    style={"color": "#4656a8"},
                    fields=layer_manifest.fields,
                    performance={
                        "source_id": f"workspace-package:{workspace_uuid}",
                        "dataset_id": dataset_id,
                        "container": f"{workspace_name}.womap.zip",
                        "layer_name": layer_manifest.name,
                        "fingerprint": layer_manifest.fingerprint,
                        "staging": True,
                        "import_job_id": job.id,
                    },
                    data_path=None,
                    visible=False,
                    locked=False,
                    opacity=layer_manifest.config.opacity,
                )
                self.repository.session.add(layer)
                await self.repository.session.flush()
                features = []
                for row_index, row in enumerate(rows, start=1):
                    geometry = row["geometry"]
                    min_x, min_y, max_x, max_y = geometry.bounds
                    source_feature_id = row["source_feature_id"] or (
                        f"workspace:{workspace_uuid}:{layer_manifest.original_layer_id}:{row_index}"
                    )
                    features.append(
                        MapFeature(
                            layer_id=layer.id,
                            source_feature_id=source_feature_id,
                            geom=from_shape(geometry, srid=3857),
                            properties=row["properties"],
                            bbox={
                                "min_x": float(min_x),
                                "min_y": float(min_y),
                                "max_x": float(max_x),
                                "max_y": float(max_y),
                            },
                            area=float(geometry.area) if "Polygon" in geometry.geom_type else None,
                            perimeter=float(geometry.length) if "Polygon" in geometry.geom_type else None,
                            revision=1,
                        )
                    )
                self.repository.session.add_all(features)
                layer.performance = {**layer.performance, "staging": False}
                layer.visible = layer_manifest.config.visible
                imported_configs.append(
                    WorkspaceLayerConfig(
                        layer_id=layer.id,
                        dataset_id=dataset_id,
                        visible=layer_manifest.config.visible,
                        opacity=layer_manifest.config.opacity,
                        order=len(imported_configs),
                        selection=WorkspaceFeatureSelection(mode="all"),
                    )
                )
            provider_ids = {provider.id for provider in self.settings.maps.enabled_providers}
            fallback = next(iter(provider_ids), "osm")
            basemap_id = manifest.basemap.id if manifest.basemap.id in provider_ids else fallback
            definition = WorkspaceDefinition(
                workspace_uuid=workspace_uuid,
                revision=revision,
                description=manifest.description,
                view=manifest.view,
                layers=imported_configs,
            )
            if target is None:
                target = Project(
                    name=workspace_name,
                    default_basemap=basemap_id,
                    current_view=definition.model_dump(mode="json"),
                )
                self.repository.session.add(target)
            else:
                target.default_basemap = basemap_id
                target.current_view = definition.model_dump(mode="json")
            await self.repository.session.commit()
            await self.repository.session.refresh(target)
            return target, warnings
        except Exception:
            await self.repository.session.rollback()
            for asset in installed_assets:
                asset.unlink(missing_ok=True)
            raise

    def _install_raster_asset(
        self, source: Path, fingerprint: str | None
    ) -> tuple[Path, dict, dict[str, float]]:
        storage = RasterStorage(
            self.settings.imports.raster_store_path,
            self.settings.imports.raster_scratch_path,
            self.settings.imports.raster_quota_gb,
        )
        storage.preflight(source.stat().st_size)
        metadata, bounds = RasterProcessor.inspect(source)
        digest = fingerprint or self._sha256(source)
        temporary = storage.scratch / f"package-{uuid4().hex}.tif"
        destination = storage.root / f"workspace-{uuid4().hex[:16]}-{digest[:16]}.tif"
        try:
            shutil.copyfile(source, temporary)
            temporary.replace(destination)
            return destination, metadata, bounds
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    async def download_path(self, job_id: str) -> tuple[Path, str]:
        job = await self.repository.get_job(job_id)
        if job is None or job.job_type != "workspace-export" or job.status != "done":
            raise KeyError(job_id)
        filename = (job.result or {}).get("artifact_name")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise WorkspacePackageError("工作空间包产物记录无效。")
        path = (ARTIFACT_ROOT / job.id / filename).resolve()
        if path.parent != (ARTIFACT_ROOT / job.id).resolve() or not path.is_file():
            raise KeyError(job_id)
        return path, filename

    @staticmethod
    async def _copy_name(base: str, repository: WorkspaceRepository) -> str:
        candidate = f"{base} - 副本"
        index = 2
        while await repository.name_exists(candidate):
            candidate = f"{base} - 副本 {index}"
            index += 1
        return candidate[:120]

    @staticmethod
    def _rows_bounds(rows: list[dict]) -> dict[str, float]:
        if not rows:
            return {}
        bounds = [row["geometry"].bounds for row in rows]
        return {
            "min_x": float(min(item[0] for item in bounds)),
            "min_y": float(min(item[1] for item in bounds)),
            "max_x": float(max(item[2] for item in bounds)),
            "max_y": float(max(item[3] for item in bounds)),
        }

    @staticmethod
    def _upload_path(token: str) -> Path:
        if not token or any(character not in "0123456789abcdef" for character in token.lower()):
            raise WorkspacePackageError("工作空间包上传令牌无效。")
        path = (UPLOAD_ROOT / f"{token}.womap.zip").resolve()
        if path.parent != UPLOAD_ROOT.resolve() or not path.is_file():
            raise WorkspacePackageError("工作空间包上传已失效，请重新选择文件。")
        return path


async def execute_workspace_package_job(job_id: str, session_factory=AsyncSessionLocal) -> None:
    async with session_factory() as session:
        repository = WorkspacePackageRepository(session)
        service = WorkspacePackageService(
            repository,
            WorkspaceService(WorkspaceRepository(session)),
        )
        await service.run_job(job_id)


def workspace_package_job_status(job) -> JobStatus:
    return JobRepository.to_status(job)
