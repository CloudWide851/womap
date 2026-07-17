import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.shared.config import DatabaseSettings, get_settings
from app.shared.system_resources import detect_memory_bytes


def create_database_engine(
    database: DatabaseSettings,
    *,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    pool_timeout: int | None = None,
    pool_recycle: int | None = None,
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
    return create_async_engine(database.sqlalchemy_url(), **options)

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
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


def create_worker_database() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    worker = get_settings().performance.worker
    worker_engine = create_database_engine(
        get_settings().database,
        pool_size=worker.database_pool_size,
        max_overflow=0,
        pool_timeout=worker.database_timeout_seconds,
        pool_recycle=worker.database_recycle_seconds,
    )
    return worker_engine, async_sessionmaker(worker_engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
