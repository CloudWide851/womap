from fastapi import FastAPI

from app.features.auth.dependencies import AuthPrincipal, require_csrf, require_session
from app.shared.gdal import configure_bundled_gdal


configure_bundled_gdal()


def allow_test_auth(app: FastAPI) -> FastAPI:
    principal = AuthPrincipal(username="test-user", session=None)
    app.dependency_overrides[require_session] = lambda: principal
    app.dependency_overrides[require_csrf] = lambda: principal
    return app
