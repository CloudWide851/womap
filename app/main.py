from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.shared.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app.name,
        version=settings.app.version,
        description="WOMAP local GIS workspace service.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str | bool]:
        return {
            "status": "ok",
            "environment": settings.app.environment,
            "config_source": settings.config_source,
            "database": settings.database.kind,
            "postgis_target": settings.database.uses_postgis,
            "redis_configured": settings.redis.configured,
        }

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
