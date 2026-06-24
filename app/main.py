from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="WOMAP local GIS workspace service.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str | bool]:
        return {
            "status": "ok",
            "environment": settings.app_env,
            "database": settings.database_kind,
            "redis_configured": bool(settings.redis_url),
        }

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
