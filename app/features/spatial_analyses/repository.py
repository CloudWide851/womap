from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.jobs.repository import JobRepository
from app.features.jobs.execution import apply_job_lifecycle, assert_job_execution
from app.features.jobs.policies import new_job_runtime_fields
from app.features.jobs.schemas import JobStatus, SpatialAnalysisJobProgressDetail
from app.models.job import Job
from app.models.layer import Layer


class SpatialAnalysisRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def has_active_analysis(self, workspace_id: int) -> bool:
        jobs = (
            await self.session.scalars(
                select(Job).where(
                    Job.job_type == "spatial-analysis",
                    Job.status.in_(["queued", "running"]),
                )
            )
        ).all()
        return any(int((job.payload or {}).get("workspace_id") or 0) == workspace_id for job in jobs)

    async def create_job(self, payload: dict[str, Any], total_layers: int) -> JobStatus:
        workspace_id = int(payload["workspace_id"])
        if await self.has_active_analysis(workspace_id):
            raise RuntimeError("当前工作空间已有空间分析任务正在执行。")
        detail = SpatialAnalysisJobProgressDetail(
            workspace_id=workspace_id,
            target_feature_id=int(payload["target_feature_id"]),
            total_layers=total_layers,
        )
        job = Job(
            id=f"spatial-analysis-{uuid4().hex}",
            job_type="spatial-analysis",
            status="queued",
            progress=0,
            message="空间分析任务已进入队列。",
            payload=payload,
            result={"detail": detail.model_dump(), "groups": []},
            **new_job_runtime_fields("spatial-analysis"),
        )
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return JobRepository.to_status(job)

    async def create_export_job(self, analysis_job: Job) -> JobStatus:
        detail = SpatialAnalysisJobProgressDetail(
            stage="queued",
            workspace_id=int((analysis_job.payload or {}).get("workspace_id") or 0),
            target_feature_id=int((analysis_job.payload or {}).get("target_feature_id") or 0),
        )
        job = Job(
            id=f"spatial-analysis-export-{uuid4().hex}",
            job_type="spatial-analysis-export",
            status="queued",
            progress=0,
            message="分析结果导出已进入队列。",
            payload={"analysis_job_id": analysis_job.id},
            result={"detail": detail.model_dump()},
            **new_job_runtime_fields("spatial-analysis-export"),
        )
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return JobRepository.to_status(job)

    async def get_job(self, job_id: str) -> Job | None:
        return await self.session.get(Job, job_id)

    async def request_cancel(self, job: Job) -> None:
        await self.session.refresh(job)
        detail = SpatialAnalysisJobProgressDetail.model_validate(
            (job.result or {}).get("detail") or {}
        )
        now = datetime.now(timezone.utc)
        if job.status == "queued":
            detail.stage = "canceled"
            job.status = "interrupted"
            job.finished_at = now
            job.message = "空间分析已取消。"
        else:
            detail.stage = "canceling"
            job.cancel_requested_at = now
            job.message = "已请求取消空间分析。"
        job.result = {**dict(job.result or {}), "detail": detail.model_dump()}
        await self.session.commit()

    async def update_job(
        self,
        job: Job,
        *,
        status: str | None = None,
        progress: int | None = None,
        message: str | None = None,
        detail: SpatialAnalysisJobProgressDetail | None = None,
        extra_result: dict[str, Any] | None = None,
    ) -> None:
        await assert_job_execution(self.session, job)
        apply_job_lifecycle(job, status)
        if status is not None:
            job.status = status
        if progress is not None:
            job.progress = max(0, min(100, progress))
        if message is not None:
            job.message = message
        result = dict(job.result or {})
        if detail is not None:
            result["detail"] = detail.model_dump()
        if extra_result:
            result.update(extra_result)
        job.result = result
        await self.session.commit()

    async def layer_versions(self, layer_ids: list[int]) -> dict[int, dict[str, Any]]:
        if not layer_ids:
            return {}
        layers = (await self.session.scalars(select(Layer).where(Layer.id.in_(layer_ids)))).all()
        return {
            layer.id: {
                "fingerprint": (layer.performance or {}).get("fingerprint"),
                "updated_at": layer.updated_at.isoformat() if layer.updated_at else None,
            }
            for layer in layers
        }

    async def buffer_geometry(self, target_geojson: dict[str, Any], distance_meters: float) -> dict:
        statement = text(
            """
            SELECT ST_AsGeoJSON(
              ST_Transform(
                ST_Buffer(
                  ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(:target), 3857), 4326)::geography,
                  :distance
                )::geometry,
                3857
              )
            ) AS geometry_json
            """
        )
        raw = await self.session.scalar(
            statement,
            {"target": json.dumps(target_geojson), "distance": distance_meters},
        )
        return json.loads(raw) if isinstance(raw, str) else dict(raw or {})

    async def summarize_layer(
        self,
        *,
        layer: dict[str, Any],
        target_geojson: dict[str, Any],
        target_layer_id: int,
        target_feature_id: int,
        distance_meters: float,
    ) -> dict[str, Any]:
        selection_sql, bind_values, expanding = self._selection_clause(layer)
        statement = text(
            f"""
            WITH input AS (
              SELECT ST_SetSRID(ST_GeomFromGeoJSON(:target), 3857) AS target_3857
            ), analysis AS (
              SELECT
                target_3857,
                ST_Transform(target_3857, 4326) AS target_4326,
                ST_Transform(target_3857, 4326)::geography AS target_geog,
                ST_Buffer(
                  ST_Transform(target_3857, 4326)::geography,
                  :distance
                )::geometry AS buffer_4326
              FROM input
            ), candidates AS (
              SELECT
                c.id,
                c.geom,
                ST_Transform(c.geom, 4326) AS geom_4326,
                GeometryType(c.geom) AS geom_type
              FROM map_features c CROSS JOIN analysis a
              WHERE c.layer_id = :layer_id
                AND NOT (c.layer_id = :target_layer_id AND c.id = :target_feature_id)
                {selection_sql}
                AND c.geom && ST_Transform(ST_Envelope(a.buffer_4326), 3857)
                AND ST_DWithin(
                  ST_Transform(c.geom, 4326)::geography,
                  a.target_geog,
                  :distance
                )
            ), measured AS (
              SELECT
                c.*,
                ST_Intersects(c.geom, a.target_3857) AS direct_hit,
                ST_Intersects(c.geom_4326, a.buffer_4326) AS buffer_hit,
                ST_Distance(c.geom_4326::geography, a.target_geog) AS distance_m,
                CASE WHEN c.geom_type IN ('POLYGON', 'MULTIPOLYGON') THEN
                  ST_Area(ST_Intersection(c.geom_4326, a.target_4326)::geography)
                  ELSE 0 END AS direct_area,
                CASE WHEN c.geom_type IN ('POLYGON', 'MULTIPOLYGON') THEN
                  ST_Area(ST_Intersection(c.geom_4326, a.buffer_4326)::geography)
                  ELSE 0 END AS buffer_area,
                CASE WHEN c.geom_type IN ('POLYGON', 'MULTIPOLYGON') THEN
                  ST_Area(c.geom_4326::geography) ELSE 0 END AS candidate_area,
                CASE WHEN c.geom_type IN ('LINESTRING', 'MULTILINESTRING') THEN
                  ST_Length(ST_Intersection(c.geom_4326, a.target_4326)::geography)
                  ELSE 0 END AS direct_length,
                CASE WHEN c.geom_type IN ('LINESTRING', 'MULTILINESTRING') THEN
                  ST_Length(ST_Intersection(c.geom_4326, a.buffer_4326)::geography)
                  ELSE 0 END AS buffer_length
              FROM candidates c CROSS JOIN analysis a
            )
            SELECT
              COUNT(*)::bigint AS hit_count,
              MIN(distance_m) AS nearest_distance_m,
              COUNT(*) FILTER (WHERE direct_hit)::bigint AS direct_count,
              COUNT(*) FILTER (WHERE buffer_hit)::bigint AS buffer_count,
              COALESCE(SUM(direct_area), 0) AS direct_area_sqm,
              COALESCE(SUM(buffer_area), 0) AS buffer_area_sqm,
              COALESCE(SUM(candidate_area), 0) AS candidate_area_sqm,
              COALESCE(SUM(direct_length), 0) AS direct_length_m,
              COALESCE(SUM(buffer_length), 0) AS buffer_length_m,
              COUNT(*) FILTER (WHERE geom_type IN ('POINT', 'MULTIPOINT'))::bigint AS point_count
            FROM measured
            """
        )
        if expanding:
            statement = statement.bindparams(*expanding)
        row = (
            await self.session.execute(
                statement,
                {
                    "target": json.dumps(target_geojson),
                    "distance": distance_meters,
                    "layer_id": int(layer["layer_id"]),
                    "target_layer_id": target_layer_id,
                    "target_feature_id": target_feature_id,
                    **bind_values,
                },
            )
        ).mappings().one()
        candidate_area = float(row["candidate_area_sqm"] or 0)
        buffer_area = float(row["buffer_area_sqm"] or 0)
        return {
            "hit_count": int(row["hit_count"] or 0),
            "nearest_distance_m": (
                float(row["nearest_distance_m"]) if row["nearest_distance_m"] is not None else None
            ),
            "direct_intersection_count": int(row["direct_count"] or 0),
            "buffer_intersection_count": int(row["buffer_count"] or 0),
            "direct_area_sqm": float(row["direct_area_sqm"] or 0),
            "buffer_area_sqm": buffer_area,
            "direct_length_m": float(row["direct_length_m"] or 0),
            "buffer_length_m": float(row["buffer_length_m"] or 0),
            "point_hit_count": int(row["point_count"] or 0),
            "coverage_ratio": buffer_area / candidate_area if candidate_area > 0 else None,
        }

    async def list_layer_hits(
        self,
        *,
        layer: dict[str, Any],
        target_geojson: dict[str, Any],
        target_layer_id: int,
        target_feature_id: int,
        distance_meters: float,
        after_id: int,
        limit: int,
        include_geometry: bool = False,
    ) -> tuple[list[dict[str, Any]], bool]:
        selection_sql, bind_values, expanding = self._selection_clause(layer)
        geometry_select = ", ST_AsGeoJSON(c.geom) AS geometry_json" if include_geometry else ""
        statement = text(
            f"""
            WITH input AS (
              SELECT ST_SetSRID(ST_GeomFromGeoJSON(:target), 3857) AS target_3857
            ), analysis AS (
              SELECT
                target_3857,
                ST_Transform(target_3857, 4326) AS target_4326,
                ST_Transform(target_3857, 4326)::geography AS target_geog,
                ST_Buffer(ST_Transform(target_3857, 4326)::geography, :distance)::geometry AS buffer_4326
              FROM input
            )
            SELECT
              c.id,
              c.source_feature_id,
              c.properties,
              GeometryType(c.geom) AS geom_type,
              ST_Intersects(c.geom, a.target_3857) AS direct_hit,
              ST_Intersects(ST_Transform(c.geom, 4326), a.buffer_4326) AS buffer_hit,
              ST_Distance(ST_Transform(c.geom, 4326)::geography, a.target_geog) AS distance_m,
              CASE WHEN GeometryType(c.geom) IN ('POLYGON', 'MULTIPOLYGON') THEN
                ST_Area(ST_Intersection(ST_Transform(c.geom, 4326), a.buffer_4326)::geography)
                ELSE 0 END AS intersection_area,
              CASE WHEN GeometryType(c.geom) IN ('LINESTRING', 'MULTILINESTRING') THEN
                ST_Length(ST_Intersection(ST_Transform(c.geom, 4326), a.buffer_4326)::geography)
                ELSE 0 END AS intersection_length
              {geometry_select}
            FROM map_features c CROSS JOIN analysis a
            WHERE c.layer_id = :layer_id
              AND c.id > :after_id
              AND NOT (c.layer_id = :target_layer_id AND c.id = :target_feature_id)
              {selection_sql}
              AND c.geom && ST_Transform(ST_Envelope(a.buffer_4326), 3857)
              AND ST_DWithin(ST_Transform(c.geom, 4326)::geography, a.target_geog, :distance)
            ORDER BY c.id
            LIMIT :row_limit
            """
        )
        if expanding:
            statement = statement.bindparams(*expanding)
        rows = (
            await self.session.execute(
                statement,
                {
                    "target": json.dumps(target_geojson),
                    "distance": distance_meters,
                    "layer_id": int(layer["layer_id"]),
                    "target_layer_id": target_layer_id,
                    "target_feature_id": target_feature_id,
                    "after_id": after_id,
                    "row_limit": limit + 1,
                    **bind_values,
                },
            )
        ).mappings().all()
        has_more = len(rows) > limit
        result = []
        for row in rows[:limit]:
            properties = dict(row["properties"] or {})
            raw_geometry = row.get("geometry_json")
            result.append(
                {
                    "feature_id": int(row["id"]),
                    "source_feature_id": row["source_feature_id"],
                    "label": self._feature_label(properties, int(row["id"])),
                    "geometry_type": str(row["geom_type"]),
                    "direct_intersection": bool(row["direct_hit"]),
                    "buffer_intersection": bool(row["buffer_hit"]),
                    "distance_m": float(row["distance_m"] or 0),
                    "intersection_area_sqm": float(row["intersection_area"] or 0),
                    "intersection_length_m": float(row["intersection_length"] or 0),
                    "properties": properties,
                    "geometry": json.loads(raw_geometry) if isinstance(raw_geometry, str) else raw_geometry,
                }
            )
        return result, has_more

    async def rollback(self) -> None:
        await self.session.rollback()

    @staticmethod
    def _selection_clause(layer: dict[str, Any]):
        selection = layer.get("selection") or {}
        if selection.get("mode") != "include":
            return "", {}, []
        feature_ids = [int(value) for value in selection.get("feature_ids") or []]
        source_ids = [str(value) for value in selection.get("source_feature_ids") or []]
        clauses = []
        values: dict[str, Any] = {}
        expanding = []
        if feature_ids:
            clauses.append("c.id IN :feature_ids")
            values["feature_ids"] = feature_ids
            expanding.append(bindparam("feature_ids", expanding=True))
        if source_ids:
            clauses.append("c.source_feature_id IN :source_feature_ids")
            values["source_feature_ids"] = source_ids
            expanding.append(bindparam("source_feature_ids", expanding=True))
        return (f"AND ({' OR '.join(clauses)})" if clauses else "AND FALSE"), values, expanding

    @staticmethod
    def _feature_label(properties: dict[str, Any], feature_id: int) -> str:
        for key in ("name", "名称", "title", "标题", "编号", "code"):
            value = properties.get(key)
            if value not in (None, ""):
                return str(value)
        return f"图斑 {feature_id}"
