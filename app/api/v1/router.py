from fastapi import APIRouter

from app.api.v1.routes import layers, projects

api_router = APIRouter()
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(layers.router, prefix="/layers", tags=["layers"])
