import os
import time
from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool, PoolProxiedConnection

from app.shared.config import DatabaseSettings, get_settings
from app.shared.system_resources import detect_memory_bytes
from app.shared.runtime_metrics import runtime_metrics


class InstrumentedAsyncAdaptedQueuePool(AsyncAdaptedQueuePool):
    metrics_pool_name = "database"

    def connect(self) -> PoolProxiedConnection:
        started = time.perf_counter()
        try:
            connection = super().connect()
        except SqlAlchemyTimeoutError:
            runtime_metrics.pool_timeout(self.metrics_pool_name)
            raise
        runtime_metrics.pool_acquire(
            self.metrics_pool_name,
            (time.perf_counter() - started) * 1000,
        )
        return connection


class InstrumentedAsyncSession(AsyncSession):
    async def __aenter__(self) -> "InstrumentedAsyncSession":
        await super().__aenter__()
        if self.bind is not None and self.bind.dialect.name == "postgresql":
            # PostgreSQL wait metrics are captured by the pool itself so a
            # session that never runs SQL keeps SQLAlchemy's lazy checkout.
            return self
        pool_name = str(self.info.get("metrics_pool") or "database")
        started = time.perf_counter()
        try:
            await self.connection()
        except SqlAlchemyTimeoutError:
            runtime_metrics.pool_timeout(pool_name)
            raise
        else:
            runtime_metrics.pool_acquire(pool_name, (time.perf_counter() - started) * 1000)
        return self


def _instrument_engine(engine: AsyncEngine, pool_name: str) -> None:
    @event.listens_for(engine.sync_engine, "checkout")
    def _checkout(*_arguments: object) -> None:
        runtime_metrics.pool_checkout(pool_name)

    @event.listens_for(engine.sync_engine, "checkin")
    def _checkin(*_arguments: object) -> None:
        runtime_metrics.pool_checkin(pool_name)


def create_database_engine(
    database: DatabaseSettings,
    *,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    pool_timeout: int | None = None,
    pool_recycle: int | None = None,
    metrics_pool: str | None = None,
) -> AsyncEngine:
    options: dict[str, object] = {
        "pool_pre_ping": True,
        "connect_args": database.connect_args(),
    }
    if database.kind == "postgresql":
        options.update(
            pool_size=pool_size or database.pool.max_size,
            max_overflow=max_overflow if max_overflow is not None else 0,
            pool_timeout=pool_timeout or database.pool.timeout_seconds,
            pool_recycle=pool_recycle or 1800,
        )
        if metrics_pool:
            options["poolclass"] = InstrumentedAsyncAdaptedQueuePool
    engine = create_async_engine(database.sqlalchemy_url(), **options)
    if metrics_pool:
        if isinstance(engine.sync_engine.pool, InstrumentedAsyncAdaptedQueuePool):
            engine.sync_engine.pool.metrics_pool_name = metrics_pool
        _instrument_engine(engine, metrics_pool)
    return engine

settings = get_settings()
total_memory_bytes, _ = detect_memory_bytes()
resolved_performance = settings.performance.resolve(
    logical_cpu_count=os.cpu_count(),
    total_memory_bytes=total_memory_bytes,
)
engine = create_database_engine(
    settings.database,
    pool_size=resolved_performance.database_pool_size,
    max_overflow=resolved_performance.database_max_overflow,
    pool_timeout=settings.performance.api.database_timeout_seconds,
    pool_recycle=settings.performance.api.database_recycle_seconds,
    metrics_pool="api",
)
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=InstrumentedAsyncSession,
    expire_on_commit=False,
    info={"metrics_pool": "api"},
)


def create_worker_database() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    worker = get_settings().performance.worker
    worker_engine = create_database_engine(
        get_settings().database,
        pool_size=worker.database_pool_size,
        max_overflow=0,
        pool_timeout=worker.database_timeout_seconds,
        pool_recycle=worker.database_recycle_seconds,
        metrics_pool="worker",
    )
    return worker_engine, async_sessionmaker(
        worker_engine,
        class_=InstrumentedAsyncSession,
        expire_on_commit=False,
        info={"metrics_pool": "worker"},
    )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
