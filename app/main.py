import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.router import api_router
from app.shared.cache import close_performance_cache
from app.shared.config import get_settings
from app.shared.database import AsyncSessionLocal, engine
from app.shared.frontend_runtime import register_frontend_runtime

logger = logging.getLogger("womap.lifecycle")


def _security_headers(request_id: str) -> dict[str, str]:
    return {
        "X-Request-ID": request_id,
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        yield
    finally:
        await close_performance_cache()
        await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app.name,
        version=settings.app.version,
        description="WOMAP local GIS workspace service.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.server.trusted_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(HTTPException)
    async def public_http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "request_id": getattr(request.state, "request_id", "unavailable"),
            },
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def public_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        errors = [
            {
                "location": list(error.get("loc", ())),
                "message": error.get("msg", "参数无效"),
                "type": error.get("type", "validation_error"),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "detail": "请求参数无效。",
                "errors": errors,
                "request_id": getattr(request.state, "request_id", "unavailable"),
            },
        )

    @app.exception_handler(Exception)
    async def public_internal_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unavailable")
        logger.error(
            "unhandled_request_error request_id=%s path=%s error_type=%s",
            request_id,
            request.url.path,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "服务处理请求时发生错误。",
                "request_id": request_id,
            },
            headers=_security_headers(request_id),
        )

    @app.middleware("http")
    async def add_request_context(request: Request, call_next):
        request_id = uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers.update(_security_headers(request_id))
        return response

    @app.get("/health/live", tags=["system"])
    async def health_live() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/health/ready", tags=["system"])
    async def health_ready() -> JSONResponse:
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
        except Exception as exc:
            logger.warning("readiness_failed error_type=%s", type(exc).__name__)
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "not_ready"},
            )
        return JSONResponse(content={"status": "ready"})

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "alive"}

    app.include_router(api_router, prefix="/api/v1")
    if settings.runtime.mode == "production":
        register_frontend_runtime(app)
    return app


app = create_app()
