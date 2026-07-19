from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.features.performance.service import PerformanceService
from app.features.rasters.processor import RasterProcessor
from app.features.rasters.schemas import RasterHistogramResponse
from app.features.rasters.service import RasterService
from app.features.rasters.storage import RasterStorage
from app.shared.cache import RedisJsonCache
from app.shared.config import PerformanceSettings, Settings
from app.shared.database import InstrumentedAsyncSession, create_database_engine
from app.shared.runtime_metrics import runtime_metrics
from scripts.perf.capture_postgis_plans import summarize_plan


class FakeRedis:
    def __init__(self, *, fail: bool = False) -> None:
        self.values: dict[str, str] = {}
        self.expiries: dict[str, int] = {}
        self.deleted: list[str] = []
        self.fail = fail

    async def get(self, key: str) -> str | None:
        if self.fail:
            raise TimeoutError
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> None:
        if self.fail:
            raise TimeoutError
        self.values[key] = value
        self.expiries[key] = ex

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.values.pop(key, None)


def _histogram() -> RasterHistogramResponse:
    return RasterHistogramResponse(
        layer_id=7,
        band=1,
        bins=[1, 2],
        edges=[0.0, 1.0, 2.0],
        minimum=0,
        maximum=2,
        percentiles={"p2": 0, "p50": 1, "p98": 2},
        sample_count=3,
    )


@pytest.mark.asyncio
async def test_redis_json_cache_validates_ttl_corruption_oversize_and_fail_open() -> None:
    runtime_metrics.reset()
    client = FakeRedis()
    cache = RedisJsonCache(
        client,  # type: ignore[arg-type]
        namespace="womap:test",
        ttl_seconds=45,
        max_entry_bytes=4096,
    )

    assert (await cache.get("histogram:v1", RasterHistogramResponse)).hit is False
    assert await cache.set("histogram:v1", _histogram()) is True
    lookup = await cache.get("histogram:v1", RasterHistogramResponse)
    assert lookup.hit is True
    assert lookup.value == _histogram()
    assert set(client.expiries.values()) == {45}

    stored_key = next(iter(client.values))
    client.values[stored_key] = "not-json"
    corrupted = await cache.get("histogram:v1", RasterHistogramResponse)
    assert corrupted.hit is False
    assert stored_key in client.deleted

    tiny = RedisJsonCache(
        client,  # type: ignore[arg-type]
        namespace="womap:test",
        ttl_seconds=45,
        max_entry_bytes=8,
    )
    assert await tiny.set("large", _histogram()) is False

    unavailable = RedisJsonCache(
        FakeRedis(fail=True),  # type: ignore[arg-type]
        namespace="womap:test",
        ttl_seconds=45,
        max_entry_bytes=4096,
    )
    assert (await unavailable.get("fallback", RasterHistogramResponse)).value is None
    metrics = runtime_metrics.snapshot()["cache"]
    assert metrics["hit"] == 1
    assert metrics["corruption"] == 1
    assert metrics["oversize"] == 1
    assert metrics["error"] == 1


def test_gdal_budget_and_formula_windows_are_bounded(tmp_path: Path) -> None:
    resolved = PerformanceSettings.model_validate(
        {
            "profile": "balanced",
            "gdal": {
                "thread_cap": 3,
                "cache_mib": 320,
                "dataset_pool_size": 40,
                "formula_window_budget_mib": 32,
                "scratch_reserve_gib": 1,
            },
        }
    ).resolve(logical_cpu_count=16, total_memory_bytes=64 * 1024**3)
    processor = RasterProcessor(
        RasterStorage(str(tmp_path / "store"), str(tmp_path / "scratch"), 2),
        resolved,
    )

    assert processor._gdal_env() == {
        "GDAL_CACHEMAX": 320,
        "GDAL_NUM_THREADS": "3",
        "GDAL_MAX_DATASET_POOL_SIZE": 40,
    }
    width, height, count = processor._formula_window_plan(10_000, 8_000, 4)
    windows = processor._iter_windows(10_000, 8_000, width, height)
    assert width * height * (4 + 4) * 4 <= 32 * 1024**2
    assert sum(1 for _ in windows) == count


def test_scratch_preflight_accounts_for_formula_and_reserve(tmp_path: Path) -> None:
    storage = RasterStorage(str(tmp_path / "store"), str(tmp_path / "scratch"), 2)
    estimate = storage.preflight(
        128 * 1024**2,
        operation="formula",
        reserve_bytes=64 * 1024**2,
    )

    assert estimate.formula_intermediate_bytes == estimate.final_asset_bytes
    assert estimate.scratch_required_bytes > estimate.final_asset_bytes * 2
    assert estimate.store_required_bytes == estimate.final_asset_bytes
    assert estimate.reserve_bytes == 64 * 1024**2


@pytest.mark.asyncio
async def test_database_pool_metrics_are_bounded_and_public() -> None:
    runtime_metrics.reset()
    settings = Settings.model_validate(
        {"database": {"driver": "sqlite+aiosqlite", "name": ":memory:"}}
    )
    engine = create_database_engine(settings.database, metrics_pool="test-api")
    sessions = async_sessionmaker(
        engine,
        class_=InstrumentedAsyncSession,
        expire_on_commit=False,
        info={"metrics_pool": "test-api"},
    )
    try:
        async with sessions() as session:
            assert await session.scalar(text("SELECT 1")) == 1
    finally:
        await engine.dispose()

    response = await PerformanceService(settings=settings).get_metrics()
    pool = response.database_pools["test-api"]
    assert pool.checkouts == 1
    assert pool.peak == 1
    assert pool.samples == 1
    assert response.connection_budget.server_max_connections is None
    serialized = response.model_dump_json()
    assert "sqlite" not in serialized
    assert "password" not in serialized.casefold()


@pytest.mark.asyncio
async def test_postgresql_pool_metrics_preserve_lazy_session_checkout() -> None:
    runtime_metrics.reset()
    settings = Settings.model_validate(
        {
            "database": {
                "driver": "postgresql+asyncpg",
                "host": "127.0.0.1",
                "name": "womap",
            }
        }
    )
    engine = create_database_engine(settings.database, metrics_pool="lazy-postgresql")
    sessions = async_sessionmaker(
        engine,
        class_=InstrumentedAsyncSession,
        expire_on_commit=False,
        info={"metrics_pool": "lazy-postgresql"},
    )
    try:
        async with sessions():
            pass
    finally:
        await engine.dispose()

    assert "lazy-postgresql" not in runtime_metrics.snapshot()["database_pools"]


def test_postgis_plan_summary_reports_index_blocks_sort_and_bad_statistics() -> None:
    plan: list[dict[str, Any]] = [
        {
            "Planning Time": 1.2,
            "Execution Time": 8.5,
            "Plan": {
                "Node Type": "Sort",
                "Plan Rows": 1,
                "Actual Rows": 100,
                "Sort Method": "quicksort",
                "Shared Hit Blocks": 12,
                "Plans": [
                    {
                        "Node Type": "Index Scan",
                        "Index Name": "ix_map_features_geom_gist",
                        "Plan Rows": 100,
                        "Actual Rows": 100,
                        "Temp Read Blocks": 2,
                    }
                ],
            },
        }
    ]

    summary = summarize_plan(plan)

    assert summary["indexes"] == ["ix_map_features_geom_gist"]
    assert summary["shared_blocks"] == 12
    assert summary["temporary_blocks"] == 2
    assert summary["statistics_misaligned_over_10x"] is True
    assert summary["execution_time_ms"] == 8.5


@pytest.mark.asyncio
async def test_histogram_cache_uses_asset_fingerprint_and_marks_hits(tmp_path: Path) -> None:
    path = tmp_path / "histogram.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=8,
        height=8,
        count=1,
        dtype="uint8",
        crs="EPSG:3857",
        transform=from_origin(0, 8, 1, 1),
    ) as dataset:
        dataset.write(np.arange(64, dtype="uint8").reshape(1, 8, 8))

    redis = FakeRedis()
    cache = RedisJsonCache(
        redis,  # type: ignore[arg-type]
        namespace="womap:test",
        ttl_seconds=60,
        max_entry_bytes=4096,
    )
    service = RasterService(None, cache=cache)  # type: ignore[arg-type]

    async def asset(_layer_id: int, *, visible: bool = True):
        del visible
        return path, '"asset-fingerprint"', "Tue, 15 Jul 2026 00:00:00 GMT"

    service.asset = asset  # type: ignore[method-assign]
    first = await service.histogram(7, 1, 16)
    second = await service.histogram(7, 1, 16)

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert first.bins == second.bins
