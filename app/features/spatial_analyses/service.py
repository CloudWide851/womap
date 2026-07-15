from __future__ import annotations

import asyncio
import csv
import json
import shutil
import zipfile
from collections import OrderedDict
from pathlib import Path
from typing import Any

from app.features.jobs.repository import JobRepository
from app.features.jobs.schemas import JobStatus, SpatialAnalysisJobProgressDetail
from app.features.map_features.repository import MapFeatureRepository
from app.features.map_features.service import MapFeatureService
from app.features.spatial_analyses.repository import SpatialAnalysisRepository
from app.features.spatial_analyses.schemas import (
    SpatialAnalysisCreate,
    SpatialAnalysisDatasetSummary,
    SpatialAnalysisHit,
    SpatialAnalysisHitPage,
    SpatialAnalysisLayerSummary,
    SpatialAnalysisResult,
)
from app.features.workspaces.repository import WorkspaceRepository
from app.features.workspaces.service import WorkspaceService
from app.models.job import Job
from app.shared.config import ROOT_DIR
from app.shared.database import AsyncSessionLocal

ANALYSIS_ARTIFACT_ROOT = ROOT_DIR / ".womap-data" / "spatial-analysis"
_CANCEL_REQUESTS: set[str] = set()


class SpatialAnalysisService:
    def __init__(
        self,
        repository: SpatialAnalysisRepository,
        workspace_service: WorkspaceService,
        feature_service: MapFeatureService,
    ) -> None:
        self.repository = repository
        self.workspace_service = workspace_service
        self.feature_service = feature_service

    async def queue(self, payload: SpatialAnalysisCreate) -> JobStatus:
        workspace = await self.workspace_service.get_workspace(payload.workspace_id)
        target_state = next(
            (state for state in workspace.layers if state.layer.id == payload.target_layer_id),
            None,
        )
        if (
            target_state is None
            or not target_state.config.visible
            or target_state.layer.kind == "raster"
        ):
            raise ValueError("分析目标必须来自当前工作空间的可见图层。")
        target = await self.feature_service.get_feature_detail(
            payload.target_layer_id,
            payload.target_feature_id,
            payload.workspace_id,
        )
        if target.geometry is None:
            raise ValueError("分析目标缺少有效几何。")
        layer_states = [
            state
            for state in workspace.layers
            if state.layer.kind == "vector"
            and (payload.scope == "all" or state.config.visible)
        ]
        versions = await self.repository.layer_versions([state.layer.id for state in layer_states])
        layers = []
        for state in layer_states:
            provenance = state.layer.provenance
            group_key = (
                f"{provenance.format}:{provenance.source_id or 'local'}:"
                f"{provenance.container or provenance.dataset_id or 'manual'}"
            )
            layers.append(
                {
                    "layer_id": state.layer.id,
                    "layer_name": state.layer.name,
                    "geometry_type": state.layer.geometry_type,
                    "visible": state.config.visible,
                    "selection": state.config.selection.model_dump(mode="json"),
                    "group_key": group_key,
                    "group_name": provenance.container or "本地编辑",
                    "source_type": provenance.format,
                    "version": versions.get(state.layer.id, {}),
                }
            )
        job_payload = {
            **payload.model_dump(mode="json"),
            "distance_meters": payload.distance_meters,
            "target_geometry": target.geometry.model_dump(mode="json"),
            "target_properties": target.properties,
            "layers": layers,
        }
        return await self.repository.create_job(job_payload, len(layers))

    async def run(self, job_id: str) -> None:
        job = await self.repository.get_job(job_id)
        if job is None or job.job_type != "spatial-analysis":
            return
        detail = SpatialAnalysisJobProgressDetail.model_validate(
            (job.result or {}).get("detail") or {}
        )
        try:
            detail.stage = "running"
            await self.repository.update_job(
                job,
                status="running",
                progress=1,
                message="正在按工作空间图层执行空间分析。",
                detail=detail,
            )
            payload = job.payload or {}
            buffer_geometry = await self.repository.buffer_geometry(
                payload["target_geometry"],
                float(payload["distance_meters"]),
            )
            grouped: OrderedDict[str, SpatialAnalysisDatasetSummary] = OrderedDict()
            layers = list(payload.get("layers") or [])
            for index, layer in enumerate(layers, start=1):
                if job_id in _CANCEL_REQUESTS:
                    raise asyncio.CancelledError
                metrics = await self.repository.summarize_layer(
                    layer=layer,
                    target_geojson=payload["target_geometry"],
                    target_layer_id=int(payload["target_layer_id"]),
                    target_feature_id=int(payload["target_feature_id"]),
                    distance_meters=float(payload["distance_meters"]),
                )
                summary = SpatialAnalysisLayerSummary(
                    layer_id=int(layer["layer_id"]),
                    layer_name=str(layer["layer_name"]),
                    geometry_type=str(layer["geometry_type"]),
                    exists=metrics["hit_count"] > 0,
                    **metrics,
                )
                group_key = str(layer["group_key"])
                if group_key not in grouped:
                    grouped[group_key] = SpatialAnalysisDatasetSummary(
                        key=group_key,
                        name=str(layer["group_name"]),
                        source_type=str(layer["source_type"]),
                    )
                grouped[group_key].layers.append(summary)
                detail.processed_layers = index
                detail.matched_features += summary.hit_count
                await self.repository.update_job(
                    job,
                    status="running",
                    progress=max(1, int(index / max(1, len(layers)) * 95)),
                    message=f"已分析 {index}/{len(layers)} 个图层。",
                    detail=detail,
                    extra_result={"groups": [group.model_dump() for group in grouped.values()]},
                )
            detail.stage = "done"
            await self.repository.update_job(
                job,
                status="done",
                progress=100,
                message=f"空间分析完成，共命中 {detail.matched_features} 个图斑。",
                detail=detail,
                extra_result={
                    "groups": [group.model_dump() for group in grouped.values()],
                    "target_geometry": payload["target_geometry"],
                    "buffer_geometry": buffer_geometry,
                },
            )
        except asyncio.CancelledError:
            await self.repository.rollback()
            detail.stage = "canceled"
            await self.repository.update_job(
                job,
                status="interrupted",
                message="空间分析已取消。",
                detail=detail,
            )
        except Exception as exc:
            await self.repository.rollback()
            detail.stage = "failed"
            detail.error = str(exc)
            await self.repository.update_job(
                job,
                status="failed",
                message=f"空间分析失败：{exc}",
                detail=detail,
            )
        finally:
            _CANCEL_REQUESTS.discard(job_id)

    async def get_result(self, job_id: str) -> SpatialAnalysisResult:
        job = await self._analysis_job(job_id)
        payload = job.payload or {}
        result = job.result or {}
        stale, warnings = await self._stale(payload)
        return SpatialAnalysisResult(
            job=JobRepository.to_status(job),
            workspace_id=int(payload["workspace_id"]),
            target_layer_id=int(payload["target_layer_id"]),
            target_feature_id=int(payload["target_feature_id"]),
            distance=float(payload["distance"]),
            unit=payload["unit"],
            distance_meters=float(payload["distance_meters"]),
            scope=payload["scope"],
            target_geometry=result.get("target_geometry") or payload.get("target_geometry"),
            buffer_geometry=result.get("buffer_geometry"),
            groups=[
                SpatialAnalysisDatasetSummary.model_validate(group)
                for group in result.get("groups") or []
            ],
            stale=stale,
            warnings=warnings,
        )

    async def hits(
        self,
        job_id: str,
        *,
        limit: int,
        cursor: str | None,
        include_geometry: bool = False,
    ) -> SpatialAnalysisHitPage:
        job = await self._analysis_job(job_id)
        if job.status != "done":
            raise ValueError("空间分析尚未完成。")
        payload = job.payload or {}
        layers = list(payload.get("layers") or [])
        cursor_layer, cursor_feature = self._decode_cursor(cursor)
        items: list[SpatialAnalysisHit] = []
        next_cursor = None
        has_more = False
        for layer in layers:
            layer_id = int(layer["layer_id"])
            if layer_id < cursor_layer:
                continue
            after_id = cursor_feature if layer_id == cursor_layer else 0
            rows, layer_has_more = await self.repository.list_layer_hits(
                layer=layer,
                target_geojson=payload["target_geometry"],
                target_layer_id=int(payload["target_layer_id"]),
                target_feature_id=int(payload["target_feature_id"]),
                distance_meters=float(payload["distance_meters"]),
                after_id=after_id,
                limit=limit - len(items),
                include_geometry=include_geometry,
            )
            items.extend(
                SpatialAnalysisHit(
                    layer_id=layer_id,
                    layer_name=str(layer["layer_name"]),
                    **row,
                )
                for row in rows
            )
            if layer_has_more:
                has_more = True
                next_cursor = f"{layer_id}:{items[-1].feature_id}"
                break
            if len(items) >= limit:
                following_layers = any(int(item["layer_id"]) > layer_id for item in layers)
                has_more = following_layers
                next_cursor = f"{layer_id}:{items[-1].feature_id}" if items else None
                break
        stale, warnings = await self._stale(payload)
        return SpatialAnalysisHitPage(
            items=items,
            next_cursor=next_cursor,
            has_more=has_more,
            stale=stale,
            warnings=warnings,
        )

    async def cancel(self, job_id: str) -> JobStatus:
        job = await self._analysis_job(job_id)
        if job.status not in {"queued", "running"}:
            raise ValueError("只有排队中或运行中的空间分析可以取消。")
        _CANCEL_REQUESTS.add(job_id)
        detail = SpatialAnalysisJobProgressDetail.model_validate(
            (job.result or {}).get("detail") or {}
        )
        detail.stage = "canceling"
        await self.repository.update_job(
            job,
            status="interrupted",
            message="已请求取消空间分析。",
            detail=detail,
        )
        return JobRepository.to_status(job)

    async def queue_export(self, job_id: str) -> JobStatus:
        analysis_job = await self._analysis_job(job_id)
        if analysis_job.status != "done":
            raise ValueError("空间分析完成后才能导出结果。")
        return await self.repository.create_export_job(analysis_job)

    async def run_export(self, export_job_id: str) -> None:
        export_job = await self.repository.get_job(export_job_id)
        if export_job is None or export_job.job_type != "spatial-analysis-export":
            return
        detail = SpatialAnalysisJobProgressDetail.model_validate(
            (export_job.result or {}).get("detail") or {}
        )
        try:
            analysis_job_id = str(export_job.payload["analysis_job_id"])
            result = await self.get_result(analysis_job_id)
            detail.stage = "exporting"
            await self.repository.update_job(
                export_job,
                status="running",
                progress=5,
                message="正在导出分析摘要和命中图斑。",
                detail=detail,
            )
            hits: list[SpatialAnalysisHit] = []
            cursor = None
            while True:
                page = await self.hits(
                    analysis_job_id,
                    limit=500,
                    cursor=cursor,
                    include_geometry=True,
                )
                hits.extend(page.items)
                if not page.has_more or not page.next_cursor:
                    break
                cursor = page.next_cursor
            filename = await asyncio.to_thread(
                self._write_export,
                export_job.id,
                result,
                hits,
            )
            detail.stage = "done"
            detail.matched_features = len(hits)
            await self.repository.update_job(
                export_job,
                status="done",
                progress=100,
                message="分析结果导出已完成。",
                detail=detail,
                extra_result={"artifact_name": filename, "download_ready": True},
            )
        except Exception as exc:
            await self.repository.rollback()
            detail.stage = "failed"
            detail.error = str(exc)
            await self.repository.update_job(
                export_job,
                status="failed",
                message=f"分析结果导出失败：{exc}",
                detail=detail,
            )

    async def download_path(self, export_job_id: str) -> tuple[Path, str]:
        job = await self.repository.get_job(export_job_id)
        if job is None or job.job_type != "spatial-analysis-export" or job.status != "done":
            raise KeyError(export_job_id)
        filename = (job.result or {}).get("artifact_name")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ValueError("分析结果产物记录无效。")
        path = (ANALYSIS_ARTIFACT_ROOT / job.id / filename).resolve()
        if path.parent != (ANALYSIS_ARTIFACT_ROOT / job.id).resolve() or not path.is_file():
            raise KeyError(export_job_id)
        return path, filename

    async def _analysis_job(self, job_id: str) -> Job:
        job = await self.repository.get_job(job_id)
        if job is None or job.job_type != "spatial-analysis":
            raise KeyError(job_id)
        return job

    async def _stale(self, payload: dict[str, Any]) -> tuple[bool, list[str]]:
        layers = list(payload.get("layers") or [])
        current = await self.repository.layer_versions([int(layer["layer_id"]) for layer in layers])
        stale_layers = [
            str(layer["layer_name"])
            for layer in layers
            if current.get(int(layer["layer_id"])) != layer.get("version")
        ]
        if not stale_layers:
            return False, []
        return True, [f"分析后数据已变化：{'、'.join(stale_layers)}；结果按任务提交时的条件重新查询。"]

    @staticmethod
    def _decode_cursor(cursor: str | None) -> tuple[int, int]:
        if not cursor:
            return 0, 0
        try:
            layer_id, feature_id = cursor.split(":", maxsplit=1)
            return int(layer_id), int(feature_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("cursor 必须是 layer_id:feature_id。") from exc

    @staticmethod
    def _write_export(
        export_job_id: str,
        result: SpatialAnalysisResult,
        hits: list[SpatialAnalysisHit],
    ) -> str:
        output_dir = ANALYSIS_ARTIFACT_ROOT / export_job_id
        shutil.rmtree(output_dir, ignore_errors=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        summary_path = output_dir / "summary.csv"
        with summary_path.open("w", encoding="utf-8-sig", newline="") as file_handle:
            writer = csv.writer(file_handle)
            writer.writerow(
                [
                    "数据集",
                    "图层",
                    "几何类型",
                    "是否存在",
                    "命中数",
                    "最近距离(m)",
                    "直接相交面积(m²)",
                    "缓冲相交面积(m²)",
                    "相交长度(m)",
                    "点命中数",
                ]
            )
            for group in result.groups:
                for layer in group.layers:
                    writer.writerow(
                        [
                            group.name,
                            layer.layer_name,
                            layer.geometry_type,
                            "是" if layer.exists else "否",
                            layer.hit_count,
                            layer.nearest_distance_m,
                            layer.direct_area_sqm,
                            layer.buffer_area_sqm,
                            layer.buffer_length_m,
                            layer.point_hit_count,
                        ]
                    )
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": hit.feature_id,
                    "geometry": hit.geometry,
                    "properties": {
                        **hit.properties,
                        "womap_layer_id": hit.layer_id,
                        "womap_layer": hit.layer_name,
                        "distance_m": hit.distance_m,
                        "direct_intersection": hit.direct_intersection,
                        "intersection_area_sqm": hit.intersection_area_sqm,
                        "intersection_length_m": hit.intersection_length_m,
                    },
                }
                for hit in hits
                if hit.geometry is not None
            ],
        }
        (output_dir / "hits.geojson").write_text(
            json.dumps(geojson, ensure_ascii=False),
            encoding="utf-8",
        )
        (output_dir / "parameters.txt").write_text(
            f"workspace_id={result.workspace_id}\n"
            f"target_layer_id={result.target_layer_id}\n"
            f"target_feature_id={result.target_feature_id}\n"
            f"distance={result.distance} {result.unit}\n"
            f"scope={result.scope}\n"
            f"stale={result.stale}\n",
            encoding="utf-8",
        )
        filename = f"spatial-analysis-{result.job.id}.zip"
        with zipfile.ZipFile(output_dir / filename, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in ("summary.csv", "hits.geojson", "parameters.txt"):
                archive.write(output_dir / name, arcname=name)
        return filename


async def execute_spatial_analysis_job(job_id: str) -> None:
    async with AsyncSessionLocal() as session:
        repository = SpatialAnalysisRepository(session)
        workspace_service = WorkspaceService(WorkspaceRepository(session))
        feature_service = MapFeatureService(
            MapFeatureRepository(session),
            workspace_service,
        )
        await SpatialAnalysisService(repository, workspace_service, feature_service).run(job_id)


async def execute_spatial_analysis_export_job(job_id: str) -> None:
    async with AsyncSessionLocal() as session:
        repository = SpatialAnalysisRepository(session)
        workspace_service = WorkspaceService(WorkspaceRepository(session))
        feature_service = MapFeatureService(
            MapFeatureRepository(session),
            workspace_service,
        )
        await SpatialAnalysisService(repository, workspace_service, feature_service).run_export(job_id)
