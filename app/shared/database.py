from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.shared.config import DatabaseSettings, get_settings


def create_database_engine(database: DatabaseSettings) -> AsyncEngine:
    return create_async_engine(
        database.sqlalchemy_url(),
        pool_pre_ping=True,
        connect_args=database.connect_args(),
    )

settings = get_settings()
engine = create_database_engine(settings.database)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
