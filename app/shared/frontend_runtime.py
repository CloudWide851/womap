from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from app.shared.config import ROOT_DIR


FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
_HASHED_ASSET = re.compile(r"^assets/.+-[A-Za-z0-9_-]{8,}\.[^/]+$")


def register_frontend_runtime(app: FastAPI, dist_root: Path | None = None) -> None:
    root = (dist_root or FRONTEND_DIST).resolve()
    index_path = root / "index.html"
    if not index_path.is_file():
        raise RuntimeError("production frontend build is missing; run pnpm build first")

    @app.api_route(
        "/{frontend_path:path}",
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )
    async def frontend_file(frontend_path: str, request: Request) -> FileResponse:
        normalized = frontend_path.lstrip("/")
        first_segment = normalized.split("/", 1)[0]
        if first_segment in {"api", "health"}:
            raise HTTPException(status_code=404, detail="资源不存在。")

        candidate = (root / normalized).resolve() if normalized else index_path
        if candidate != root and root not in candidate.parents:
            raise HTTPException(status_code=404, detail="资源不存在。")
        if candidate.is_file():
            path = candidate
        elif Path(normalized).suffix:
            raise HTTPException(status_code=404, detail="资源不存在。")
        else:
            path = index_path

        relative = path.relative_to(root).as_posix()
        if path == index_path:
            cache_control = "no-cache"
        elif _HASHED_ASSET.match(relative):
            cache_control = "public, max-age=31536000, immutable"
        else:
            cache_control = "public, max-age=3600, must-revalidate"
        return FileResponse(path, headers={"Cache-Control": cache_control})
