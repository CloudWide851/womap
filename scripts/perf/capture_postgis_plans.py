from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.sql import Executable

if __package__ in {None, ""}:
    from _bootstrap import ensure_repo_root

    ensure_repo_root()

from app.features.map_features.queries import build_viewport_feature_statement
from app.features.spatial_analyses.queries import build_spatial_summary_statement
from app.shared.config import ROOT_DIR, get_settings
from app.shared.pagination import BBoxQuery
from scripts.perf.reporting import build_report, redact_report, write_report


Workload = Literal["bbox", "point", "line", "polygon"]
EXPLAIN_PREFIX = "EXPLAIN (ANALYZE, BUFFERS, SETTINGS, FORMAT JSON)\n"
PERF_ROOT = (ROOT_DIR / ".womap-data" / "perf").resolve()


def require_report_path(path: Path) -> Path:
    resolved = path.resolve()
    if resolved == PERF_ROOT or PERF_ROOT not in resolved.parents:
        raise ValueError("PostGIS plan reports must stay below .womap-data/perf")
    return resolved


def _compiled_explain(statement: Executable) -> tuple[str, dict[str, Any]]:
    compiled = statement.compile(
        dialect=postgresql.dialect(paramstyle="named"),
        compile_kwargs={"render_postcompile": True},
    )
    return EXPLAIN_PREFIX + str(compiled), dict(compiled.params)


def _analysis_target(
    workload: Workload,
    bbox: tuple[float, float, float, float],
) -> dict[str, Any]:
    min_x, min_y, max_x, max_y = bbox
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    span = max(1.0, min(max_x - min_x, max_y - min_y) * 0.02)
    if workload == "point":
        return {"type": "Point", "coordinates": [center_x, center_y]}
    if workload == "line":
        return {
            "type": "LineString",
            "coordinates": [[center_x - span, center_y], [center_x + span, center_y]],
        }
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [center_x - span, center_y - span],
                [center_x + span, center_y - span],
                [center_x + span, center_y + span],
                [center_x - span, center_y + span],
                [center_x - span, center_y - span],
            ]
        ],
    }


async def _execute_plan(
    connection: AsyncConnection,
    workload: Workload,
    *,
    layer_id: int,
    bbox: tuple[float, float, float, float],
    limit: int,
    distance_meters: float,
) -> Any:
    if workload == "bbox":
        statement = build_viewport_feature_statement(
            layer_id=layer_id,
            bbox=BBoxQuery(
                min_x=bbox[0], min_y=bbox[1], max_x=bbox[2], max_y=bbox[3]
            ),
            cursor_id=0,
            simplify=None,
            row_limit=limit,
        )
        explain_sql, parameters = _compiled_explain(statement)
    else:
        statement = build_spatial_summary_statement()
        explain_sql = EXPLAIN_PREFIX + statement.text
        parameters = {
            "target": json.dumps(_analysis_target(workload, bbox)),
            "distance": distance_meters,
            "layer_id": layer_id,
            "target_layer_id": -1,
            "target_feature_id": -1,
        }
    result = await connection.execute(text(explain_sql), parameters)
    return redact_report(result.scalar_one())


def summarize_plan(plan: Any) -> dict[str, Any]:
    root = plan[0] if isinstance(plan, list) and plan else plan
    root = root if isinstance(root, dict) else {}
    indexes: set[str] = set()
    node_types: set[str] = set()
    sort_methods: set[str] = set()
    shared_blocks = 0
    temporary_blocks = 0
    worst_row_ratio = 1.0

    def visit(node: Any) -> None:
        nonlocal shared_blocks, temporary_blocks, worst_row_ratio
        if not isinstance(node, dict):
            return
        if isinstance(node.get("Node Type"), str):
            node_types.add(node["Node Type"])
        if isinstance(node.get("Index Name"), str):
            indexes.add(node["Index Name"])
        if isinstance(node.get("Sort Method"), str):
            sort_methods.add(node["Sort Method"])
        planned = float(node.get("Plan Rows") or 0)
        actual = float(node.get("Actual Rows") or 0)
        if planned > 0 and actual > 0:
            worst_row_ratio = max(worst_row_ratio, planned / actual, actual / planned)
        elif planned != actual:
            worst_row_ratio = float("inf")
        shared_blocks += sum(
            int(node.get(key) or 0)
            for key in (
                "Shared Hit Blocks",
                "Shared Read Blocks",
                "Shared Dirtied Blocks",
                "Shared Written Blocks",
            )
        )
        temporary_blocks += int(node.get("Temp Read Blocks") or 0) + int(
            node.get("Temp Written Blocks") or 0
        )
        for child in node.get("Plans") or []:
            visit(child)

    visit(root.get("Plan"))
    ratio_value: float | str = "infinite" if worst_row_ratio == float("inf") else round(
        worst_row_ratio, 3
    )
    return {
        "indexes": sorted(indexes),
        "node_types": sorted(node_types),
        "estimated_actual_row_ratio_max": ratio_value,
        "statistics_misaligned_over_10x": worst_row_ratio > 10,
        "shared_blocks": shared_blocks,
        "temporary_blocks": temporary_blocks,
        "sort_methods": sorted(sort_methods),
        "planning_time_ms": float(root.get("Planning Time") or 0),
        "execution_time_ms": float(root.get("Execution Time") or 0),
    }


async def capture_plans(
    *,
    workloads: list[Workload],
    layer_id: int,
    bbox: tuple[float, float, float, float],
    limit: int,
    distance_meters: float,
) -> dict[str, dict[str, Any]]:
    settings = get_settings()
    if not settings.database.uses_postgis:
        raise RuntimeError("PostGIS plan capture requires the PostgreSQL runtime database")
    engine = create_async_engine(
        settings.database.sqlalchemy_url(),
        connect_args=settings.database.connect_args(),
        pool_pre_ping=True,
    )
    try:
        async with engine.connect() as connection:
            return await capture_plans_on_connection(
                connection,
                workloads=workloads,
                layer_id=layer_id,
                bbox=bbox,
                limit=limit,
                distance_meters=distance_meters,
            )
    finally:
        await engine.dispose()


async def capture_plans_on_connection(
    connection: AsyncConnection,
    *,
    workloads: list[Workload],
    layer_id: int,
    bbox: tuple[float, float, float, float],
    limit: int,
    distance_meters: float,
) -> dict[str, dict[str, Any]]:
    captured: dict[str, dict[str, Any]] = {}
    for workload in workloads:
        plan = await _execute_plan(
            connection,
            workload,
            layer_id=layer_id,
            bbox=bbox,
            limit=limit,
            distance_meters=distance_meters,
        )
        captured[workload] = {"summary": summarize_plan(plan), "plan": plan}
    return captured


async def capture_bbox_plan(
    *,
    layer_id: int,
    bbox: tuple[float, float, float, float],
    limit: int,
) -> Any:
    result = await capture_plans(
        workloads=["bbox"],
        layer_id=layer_id,
        bbox=bbox,
        limit=limit,
        distance_meters=100,
    )
    return result["bbox"]["plan"]


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    try:
        values = tuple(float(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("bbox must contain four numbers") from exc
    if len(values) != 4 or values[0] >= values[2] or values[1] >= values[3]:
        raise argparse.ArgumentTypeError("bbox must be min_x,min_y,max_x,max_y")
    min_x, min_y, max_x, max_y = values
    return min_x, min_y, max_x, max_y


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture redacted production PostGIS JSON plans.")
    parser.add_argument("--profile", choices=("ci-small", "workstation-medium"), default="ci-small")
    parser.add_argument("--layer-id", type=int, required=True)
    parser.add_argument("--bbox", type=parse_bbox, required=True)
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--distance-meters", type=float, default=100)
    parser.add_argument(
        "--workload",
        choices=("all", "bbox", "point", "line", "polygon"),
        default="all",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".womap-data/perf/reports/postgis-plans.json"),
    )
    arguments = parser.parse_args()
    if arguments.layer_id < 1:
        parser.error("layer id must be positive")
    if not 1 <= arguments.limit <= 5000:
        parser.error("limit must be between 1 and 5000")
    if not 0 < arguments.distance_meters <= 1_000_000:
        parser.error("distance-meters must be between 0 and 1000000")
    workloads: list[Workload] = (
        ["bbox", "point", "line", "polygon"]
        if arguments.workload == "all"
        else [arguments.workload]
    )
    plans = asyncio.run(
        capture_plans(
            workloads=workloads,
            layer_id=arguments.layer_id,
            bbox=arguments.bbox,
            limit=arguments.limit,
            distance_meters=arguments.distance_meters,
        )
    )
    report = build_report(
        kind="postgis-plans",
        profile=arguments.profile,
        dataset_tier=arguments.profile,
        workload={
            "queries": workloads,
            "layer_id": arguments.layer_id,
            "limit": arguments.limit,
            "explain": ["analyze", "buffers", "settings", "format-json"],
        },
        metrics={"workloads": plans},
    )
    write_report(require_report_path(arguments.output), report)
    print("PostGIS plans captured with ANALYZE, BUFFERS, SETTINGS, FORMAT JSON.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
