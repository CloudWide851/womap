import hashlib

from fastapi import APIRouter, Depends, Request, Response

from app.features.auth.cookies import clear_auth_cookies, set_auth_cookies
from app.features.auth.dependencies import AuthPrincipal, get_auth_service, require_csrf, require_session
from app.features.auth.schemas import AuthPolicyResponse, LoginRequest, LoginResponse, SessionResponse
from app.features.auth.service import AuthService
from app.shared.config import get_settings

router = APIRouter()


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


def _client_key(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    return hashlib.sha256(host.encode("utf-8")).hexdigest()


@router.get("/policy", response_model=AuthPolicyResponse)
async def get_auth_policy(service: AuthService = Depends(get_auth_service)) -> AuthPolicyResponse:
    return service.get_policy()


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    issue = await service.login(
        payload,
        client_key=_client_key(request),
        request_id=_request_id(request),
    )
    set_auth_cookies(
        response,
        session_token=issue.session_token,
        csrf_token=issue.csrf_token,
        session=issue.response,
        settings=get_settings().auth.session,
    )
    return issue.response


@router.get("/session", response_model=SessionResponse)
async def get_auth_session(
    principal: AuthPrincipal = Depends(require_session),
    service: AuthService = Depends(get_auth_service),
) -> SessionResponse:
    if principal.session is None:
        settings = get_settings().auth
        return SessionResponse(
            authenticated=True,
            username=principal.username,
            session_mode="short",
            expires_in_seconds=settings.session.idle_timeout_minutes * 60,
            renewal_in_seconds=settings.session.renewal_timeout_minutes * 60,
            policy_refresh_seconds=settings.dynamic_update.policy_refresh_seconds,
            message="认证已禁用，仅允许显式本地信任模式。",
        )
    return SessionResponse.model_validate(service.response_for(principal.session).model_dump())


@router.post("/renew", response_model=SessionResponse)
async def renew_auth_session(
    request: Request,
    response: Response,
    principal: AuthPrincipal = Depends(require_csrf),
    service: AuthService = Depends(get_auth_service),
) -> SessionResponse:
    if principal.session is None:
        return await get_auth_session(principal, service)
    issue = await service.renew(principal.session, _request_id(request))
    set_auth_cookies(
        response,
        session_token=issue.session_token,
        csrf_token=issue.csrf_token,
        session=issue.response,
        settings=get_settings().auth.session,
    )
    return SessionResponse.model_validate(issue.response.model_dump())


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    _: AuthPrincipal = Depends(require_csrf),
    service: AuthService = Depends(get_auth_service),
) -> None:
    settings = get_settings().auth.session
    await service.logout(request.cookies.get(settings.cookie_name), _request_id(request))
    clear_auth_cookies(response, settings)
