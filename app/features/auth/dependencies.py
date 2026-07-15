import hmac
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.auth.cookies import csrf_cookie_name
from app.features.auth.repository import AuthRepository
from app.features.auth.service import AuthService, hash_secret
from app.models.auth_session import AuthSession
from app.shared.config import get_settings
from app.shared.database import get_session


@dataclass(frozen=True)
class AuthPrincipal:
    username: str
    session: AuthSession | None


async def get_auth_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[AuthService, None]:
    yield AuthService(AuthRepository(session))


async def require_session(
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> AuthPrincipal:
    settings = get_settings()
    if not settings.auth.enabled:
        return AuthPrincipal(username=settings.auth.local_user.username, session=None)
    token = request.cookies.get(settings.auth.session.cookie_name)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录会话无效或已过期。",
        )
    record = await service.validate_session(token)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录会话无效或已过期。",
        )
    request.state.auth_session = record
    return AuthPrincipal(username=record.username, session=record)


async def require_csrf(
    request: Request,
    principal: AuthPrincipal = Depends(require_session),
) -> AuthPrincipal:
    if request.method in {"GET", "HEAD", "OPTIONS"} or principal.session is None:
        return principal
    settings = get_settings()
    origin = request.headers.get("origin")
    if origin and origin not in settings.server.cors_origins:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="请求来源不受信任。")
    csrf_cookie = request.cookies.get(csrf_cookie_name(settings.auth.session))
    csrf_header = request.headers.get("x-womap-csrf")
    if not csrf_cookie or not csrf_header or not hmac.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF 校验失败。")
    if not hmac.compare_digest(hash_secret(csrf_header), principal.session.csrf_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF 校验失败。")
    return principal
