import base64
import hashlib
import hmac

from fastapi import HTTPException, status

from app.features.auth.schemas import AuthPolicyResponse, LoginRequest, LoginResponse
from app.shared.config import AuthSettings, get_settings


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


class AuthService:
    def get_policy(self) -> AuthPolicyResponse:
        auth = get_settings().auth
        return self._build_policy(auth)

    def login(self, payload: LoginRequest) -> LoginResponse:
        auth = get_settings().auth
        policy = auth.password_policy
        password_length = len(payload.password)

        if password_length < policy.min_length or password_length > policy.max_length:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="登录密码长度不符合当前安全策略。",
            )

        if not auth.enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="本地登录未启用。",
            )

        local_user = auth.local_user
        if not local_user.password_configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="本地登录密码 hash 尚未在本地 YAML 中配置。",
            )

        username_matches = hmac.compare_digest(payload.username, local_user.username)
        password_matches = _verify_pbkdf2_sha256(payload.password, local_user.password_hash)
        if not username_matches or not password_matches:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="账号或密码不正确。",
            )

        return LoginResponse(
            authenticated=True,
            username=local_user.username,
            session_mode=payload.session_mode,
            expires_in_seconds=self._expires_in_seconds(auth, payload.session_mode),
            renewal_in_seconds=auth.session.renewal_timeout_minutes * 60,
            policy_refresh_seconds=auth.dynamic_update.policy_refresh_seconds,
            message="登录成功。",
        )

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

    def _expires_in_seconds(self, auth: AuthSettings, session_mode: str) -> int:
        if session_mode == "long":
            return auth.session.remember_me_days * 24 * 60 * 60
        return auth.session.idle_timeout_minutes * 60
