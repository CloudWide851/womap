from typing import Literal

from pydantic import BaseModel, Field


SessionMode = Literal["short", "long"]


class AuthPolicyResponse(BaseModel):
    enabled: bool
    username: str
    credential_configured: bool
    password_min_length: int
    password_max_length: int
    block_common_passwords: bool
    lockout_attempts: int
    lockout_window_minutes: int
    idle_timeout_minutes: int
    absolute_timeout_hours: int
    renewal_timeout_minutes: int
    remember_me_days: int
    cookie_name: str
    secure_cookie: bool
    http_only_cookie: bool
    same_site: str
    policy_refresh_seconds: int
    warn_before_expire_minutes: int
    rotate_after_login: bool
    audit_logging: bool
    redact_session_id: bool


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)
    session_mode: SessionMode = "short"


class LoginResponse(BaseModel):
    authenticated: bool
    username: str
    session_mode: SessionMode
    expires_in_seconds: int
    renewal_in_seconds: int
    policy_refresh_seconds: int
    message: str
