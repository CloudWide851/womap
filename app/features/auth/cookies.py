from fastapi import Response

from app.features.auth.schemas import LoginResponse
from app.shared.config import SessionSecuritySettings


def csrf_cookie_name(settings: SessionSecuritySettings) -> str:
    return f"{settings.cookie_name}_csrf"


def set_auth_cookies(
    response: Response,
    *,
    session_token: str,
    csrf_token: str,
    session: LoginResponse,
    settings: SessionSecuritySettings,
) -> None:
    if session.session_mode == "long":
        cookie_max_age = settings.remember_me_days * 24 * 60 * 60
    else:
        cookie_max_age = settings.absolute_timeout_hours * 60 * 60
    common = {
        "secure": settings.secure_cookie,
        "samesite": settings.same_site,
        "path": "/",
        # Server-side idle expiry remains authoritative. The browser cookie must
        # live until the absolute boundary so active sessions are not cut short.
        "max_age": cookie_max_age,
    }
    response.set_cookie(
        key=settings.cookie_name,
        value=session_token,
        httponly=settings.http_only_cookie,
        **common,
    )
    response.set_cookie(
        key=csrf_cookie_name(settings),
        value=csrf_token,
        httponly=False,
        **common,
    )


def clear_auth_cookies(response: Response, settings: SessionSecuritySettings) -> None:
    common = {
        "path": "/",
        "secure": settings.secure_cookie,
        "samesite": settings.same_site,
    }
    response.delete_cookie(key=settings.cookie_name, httponly=settings.http_only_cookie, **common)
    response.delete_cookie(key=csrf_cookie_name(settings), httponly=False, **common)
