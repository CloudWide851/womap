import base64
import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

from app.features.auth.repository import AuthRepository
from app.features.auth.schemas import AuthPolicyResponse, LoginRequest, LoginResponse
from app.features.auth.throttle import LoginThrottle, login_throttle
from app.models.auth_session import AuthSession
from app.shared.config import AuthSettings, get_settings

logger = logging.getLogger("womap.auth")


def _verify_pbkdf2_sha256(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt, digest = encoded_hash.split("$", maxsplit=3)
        iterations = int(iterations_text)
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256" or iterations < 100_000:
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    candidate_digest = base64.b64encode(candidate).decode("ascii").rstrip("=")
    return hmac.compare_digest(candidate_digest, digest)


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class SessionIssue:
    session_token: str
    csrf_token: str
    response: LoginResponse
    record: AuthSession


class AuthService:
    def __init__(
        self,
        repository: AuthRepository,
        throttle: LoginThrottle | None = None,
    ) -> None:
        self.repository = repository
        self.throttle = throttle or login_throttle

    def get_policy(self) -> AuthPolicyResponse:
        return self._build_policy(get_settings().auth)

    async def login(
        self,
        payload: LoginRequest,
        *,
        client_key: str,
        request_id: str,
    ) -> SessionIssue:
        auth = get_settings().auth
        policy = auth.password_policy
        password_length = len(payload.password)

        if password_length < policy.min_length or password_length > policy.max_length:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="登录密码长度不符合当前安全策略。",
            )
        if not auth.enabled:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="本地登录未启用。")
        if self.throttle.is_locked(
            client_key,
            limit=auth.throttling.lockout_attempts,
            window_minutes=auth.throttling.lockout_window_minutes,
        ):
            self._audit("login_throttled", payload.username, request_id)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="登录尝试过多，请稍后重试。",
            )

        local_user = auth.local_user
        if not local_user.password_configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="本地登录凭据尚未配置。",
            )

        username_matches = hmac.compare_digest(payload.username, local_user.username)
        password_matches = _verify_pbkdf2_sha256(payload.password, local_user.password_hash)
        if not username_matches or not password_matches:
            self.throttle.record_failure(
                client_key,
                window_minutes=auth.throttling.lockout_window_minutes,
            )
            self._audit("login_failed", payload.username, request_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="账号或密码不正确。",
            )

        self.throttle.reset(client_key)
        issue = await self._issue(local_user.username, payload.session_mode, auth)
        self._audit("login_succeeded", local_user.username, request_id)
        return issue

    async def validate_session(self, token: str) -> AuthSession | None:
        auth = get_settings().auth
        record = await self.repository.get_by_token_hash(hash_secret(token))
        if record is None or record.revoked_at is not None:
            return None
        now = datetime.now(timezone.utc)
        if now >= _as_utc(record.idle_expires_at) or now >= _as_utc(record.absolute_expires_at):
            await self.repository.revoke(record, now)
            return None
        idle_expires_at = min(
            now + timedelta(minutes=auth.session.idle_timeout_minutes),
            _as_utc(record.absolute_expires_at),
        )
        return await self.repository.touch(
            record,
            last_seen_at=now,
            idle_expires_at=idle_expires_at,
        )

    async def renew(self, record: AuthSession, request_id: str) -> SessionIssue:
        now = datetime.now(timezone.utc)
        await self.repository.revoke(record, now)
        issue = await self._issue(record.username, record.session_mode, get_settings().auth)
        self._audit("session_renewed", record.username, request_id)
        return issue

    async def logout(self, token: str | None, request_id: str) -> None:
        if not token:
            return
        record = await self.repository.get_by_token_hash(hash_secret(token))
        if record is None or record.revoked_at is not None:
            return
        await self.repository.revoke(record, datetime.now(timezone.utc))
        self._audit("logout", record.username, request_id)

    def response_for(self, record: AuthSession, message: str = "会话有效。") -> LoginResponse:
        now = datetime.now(timezone.utc)
        expires_at = min(_as_utc(record.idle_expires_at), _as_utc(record.absolute_expires_at))
        return LoginResponse(
            authenticated=True,
            username=record.username,
            session_mode=record.session_mode,
            expires_in_seconds=max(0, int((expires_at - now).total_seconds())),
            renewal_in_seconds=max(0, int((_as_utc(record.renew_after) - now).total_seconds())),
            policy_refresh_seconds=get_settings().auth.dynamic_update.policy_refresh_seconds,
            message=message,
        )

    async def _issue(self, username: str, session_mode: str, auth: AuthSettings) -> SessionIssue:
        now = datetime.now(timezone.utc)
        session_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        if session_mode == "long":
            absolute_expires_at = now + timedelta(days=auth.session.remember_me_days)
            idle_expires_at = absolute_expires_at
        else:
            absolute_expires_at = now + timedelta(hours=auth.session.absolute_timeout_hours)
            idle_expires_at = min(
                now + timedelta(minutes=auth.session.idle_timeout_minutes),
                absolute_expires_at,
            )
        renew_after = min(
            now + timedelta(minutes=auth.session.renewal_timeout_minutes),
            absolute_expires_at,
        )
        record = await self.repository.create_session(
            token_hash=hash_secret(session_token),
            csrf_hash=hash_secret(csrf_token),
            username=username,
            session_mode=session_mode,
            created_at=now,
            idle_expires_at=idle_expires_at,
            absolute_expires_at=absolute_expires_at,
            renew_after=renew_after,
        )
        response = self.response_for(record, "登录成功。")
        return SessionIssue(session_token, csrf_token, response, record)

    def _build_policy(self, auth: AuthSettings) -> AuthPolicyResponse:
        return AuthPolicyResponse(
            enabled=auth.enabled,
            username=auth.local_user.username,
            credential_configured=auth.local_user.password_configured,
            password_min_length=auth.password_policy.min_length,
            password_max_length=auth.password_policy.max_length,
            block_common_passwords=auth.password_policy.block_common_passwords,
            lockout_attempts=auth.throttling.lockout_attempts,
            lockout_window_minutes=auth.throttling.lockout_window_minutes,
            idle_timeout_minutes=auth.session.idle_timeout_minutes,
            absolute_timeout_hours=auth.session.absolute_timeout_hours,
            renewal_timeout_minutes=auth.session.renewal_timeout_minutes,
            remember_me_days=auth.session.remember_me_days,
            cookie_name=auth.session.cookie_name,
            secure_cookie=auth.session.secure_cookie,
            http_only_cookie=auth.session.http_only_cookie,
            same_site=auth.session.same_site,
            policy_refresh_seconds=auth.dynamic_update.policy_refresh_seconds,
            warn_before_expire_minutes=auth.dynamic_update.warn_before_expire_minutes,
            rotate_after_login=auth.dynamic_update.rotate_after_login,
            audit_logging=auth.audit.log_login_events,
            redact_session_id=auth.audit.redact_session_id,
        )

    @staticmethod
    def _audit(event: str, username: str, request_id: str) -> None:
        if not get_settings().auth.audit.log_login_events:
            return
        subject = hashlib.sha256(username.encode("utf-8")).hexdigest()[:12]
        logger.info("auth_event", extra={"event": event, "subject": subject, "request_id": request_id})
