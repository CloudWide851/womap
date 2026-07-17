from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.features.exports.service import execute_vector_export_job
from app.features.imports.service import execute_import_job
from app.features.rasters.service import execute_raster_job
from app.features.spatial_analyses.service import (
    execute_spatial_analysis_export_job,
    execute_spatial_analysis_job,
)
from app.features.workspaces.package_service import execute_workspace_package_job


JobHandler = Callable[[str, object], Awaitable[None]]


JOB_HANDLERS: dict[str, JobHandler] = {
    "import-sync": execute_import_job,
    "import-data": execute_import_job,
    "raster-derive": execute_raster_job,
    "raster-export": execute_raster_job,
    "workspace-export": execute_workspace_package_job,
    "workspace-import": execute_workspace_package_job,
    "spatial-analysis": execute_spatial_analysis_job,
    "spatial-analysis-export": execute_spatial_analysis_export_job,
    "vector-export": execute_vector_export_job,
}


async def dispatch_job(job_type: str, job_id: str, session_factory) -> None:
    try:
        handler = JOB_HANDLERS[job_type]
    except KeyError as exc:
        raise ValueError("任务类型不在 Worker 允许列表中。") from exc
    await handler(job_id, session_factory)
