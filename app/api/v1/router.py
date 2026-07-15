from fastapi import APIRouter

from app.features.auth.router import router as auth_router
from app.features.basemaps.router import router as basemaps_router
from app.features.exports.router import router as exports_router
from app.features.jobs.router import router as jobs_router
from app.features.imports.router import router as imports_router
from app.features.layers.router import router as layers_router
from app.features.map_features.router import router as map_features_router
from app.features.projects.router import router as projects_router
from app.features.rasters.router import router as rasters_router
from app.features.settings.router import router as settings_router
from app.features.spatial_analyses.router import router as spatial_analyses_router
from app.features.workspaces.router import router as workspaces_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(projects_router, prefix="/projects", tags=["projects"])
api_router.include_router(layers_router, prefix="/layers", tags=["layers"])
api_router.include_router(map_features_router, tags=["map-features"])
api_router.include_router(exports_router, prefix="/exports", tags=["exports"])
api_router.include_router(basemaps_router, prefix="/basemaps", tags=["basemaps"])
api_router.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
api_router.include_router(imports_router, prefix="/imports", tags=["imports"])
api_router.include_router(rasters_router, prefix="/rasters", tags=["rasters"])
api_router.include_router(settings_router, prefix="/settings", tags=["settings"])
api_router.include_router(workspaces_router, prefix="/workspaces", tags=["workspaces"])
api_router.include_router(
    spatial_analyses_router,
    prefix="/spatial-analyses",
    tags=["spatial-analyses"],
)
