from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

if __package__ in {None, ""}:
    from _bootstrap import ensure_repo_root

    ensure_repo_root()

from app.shared.config import get_settings
from scripts.perf.reporting import build_report, redact_report, write_report


PLAN_SQL = """
EXPLAIN (ANALYZE, BUFFERS, SETTINGS, FORMAT JSON)
SELECT id
FROM map_features
WHERE layer_id = :layer_id
  AND ST_Intersects(
    geom,
    ST_MakeEnvelope(:min_x, :min_y, :max_x, :max_y, 3857)
  )
ORDER BY id
LIMIT :limit
"""


async def capture_bbox_plan(
    *,
    layer_id: int,
    bbox: tuple[float, float, float, float],
    limit: int,
) -> Any:
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
            result = await connection.execute(
                text(PLAN_SQL),
                {
                    "layer_id": layer_id,
                    "min_x": bbox[0],
                    "min_y": bbox[1],
                    "max_x": bbox[2],
                    "max_y": bbox[3],
                    "limit": limit,
                },
            )
            return redact_report(result.scalar_one())
    finally:
        await engine.dispose()


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    try:
        values = tuple(float(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("bbox must contain four numbers") from exc
    if len(values) != 4 or values[0] >= values[2] or values[1] >= values[3]:
        raise argparse.ArgumentTypeError("bbox must be min_x,min_y,max_x,max_y")
    return values  # type: ignore[return-value]


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture a redacted PostGIS bbox JSON plan.")
    parser.add_argument("--profile", choices=("ci-small", "workstation-medium"), default="ci-small")
    parser.add_argument("--layer-id", type=int, required=True)
    parser.add_argument("--bbox", type=parse_bbox, required=True)
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".womap-data/perf/reports/postgis-bbox-plan.json"),
    )
    arguments = parser.parse_args()
    if arguments.layer_id < 1:
        parser.error("layer id must be positive")
    if not 1 <= arguments.limit <= 5000:
        parser.error("limit must be between 1 and 5000")
    plan = asyncio.run(
        capture_bbox_plan(layer_id=arguments.layer_id, bbox=arguments.bbox, limit=arguments.limit)
    )
    report = build_report(
        kind="postgis-plan",
        profile=arguments.profile,
        dataset_tier=arguments.profile,
        workload={
            "query": "bbox",
            "layer_id": arguments.layer_id,
            "bbox": arguments.bbox,
            "limit": arguments.limit,
            "explain": ["analyze", "buffers", "settings", "format-json"],
        },
        metrics={"plan": plan},
    )
    write_report(arguments.output, report)
    print("PostGIS bbox plan captured with ANALYZE, BUFFERS, SETTINGS, FORMAT JSON.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
