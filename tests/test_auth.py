from __future__ import annotations

import asyncio
import base64
import hashlib
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.features.auth.cookies import csrf_cookie_name
from app.features.auth.credentials import (
    AuthCredentialAlreadyConfiguredError,
    AuthCredentialWriteError,
    AuthCredentialWriterProtocol,
)
from app.features.auth.dependencies import get_auth_service
from app.features.auth.repository import AuthRepository
from app.features.auth.service import AuthService
from app.features.auth.throttle import LoginThrottle
from app.main import create_app
from app.models.auth_session import AuthSession
from app.shared.config import get_settings

TEST_PASSWORD = "correct horse battery staple"


def _password_hash(password: str) -> str:
    salt = "womap-test-salt"
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    encoded = base64.b64encode(digest).decode("ascii").rstrip("=")
    return f"pbkdf2_sha256$100000${salt}${encoded}"


def _auth_client(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    credential_configured: bool = True,
    credential_writer: AuthCredentialWriterProtocol | None = None,
    client_host: str = "127.0.0.1",
) -> tuple[TestClient, async_sessionmaker[AsyncSession]]:
    settings = get_settings()
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(
        settings.auth.local_user,
        "password_hash",
        _password_hash(TEST_PASSWORD) if credential_configured else "",
    )
    monkeypatch.setattr(settings.auth.session, "secure_cookie", False)

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path.as_posix()}",
        poolclass=NullPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(AuthSession.__table__.create)

    asyncio.run(prepare())
    throttle = LoginThrottle()

    async def auth_service() -> AsyncGenerator[AuthService, None]:
        async with session_factory() as session:
            yield AuthService(
                AuthRepository(session),
                throttle,
                credential_writer=credential_writer,
            )

    app = create_app()
    app.dependency_overrides[get_auth_service] = auth_service
    return TestClient(app, client=(client_host, 50000)), session_factory


class RecordingCredentialWriter:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def configure(self, username: str, password: str) -> None:
        if self.error:
            raise self.error
        self.calls.append((username, password))


def test_business_routes_require_a_valid_session() -> None:
    response = TestClient(create_app()).get("/api/v1/basemaps")

    assert response.status_code == 401
    assert "session" not in response.text.lower()


def test_login_cookie_csrf_renew_and_logout_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, session_factory = _auth_client(tmp_path / "auth.sqlite3", monkeypatch)
    settings = get_settings().auth.session

    login = client.post(
        "/api/v1/auth/login",
        json={
            "username": "local-admin",
            "password": TEST_PASSWORD,
            "session_mode": "short",
        },
    )

    assert login.status_code == 200
    assert login.json()["authenticated"] is True
    assert TEST_PASSWORD not in login.text
    assert client.cookies.get(settings.cookie_name)
    csrf_name = csrf_cookie_name(settings)
    csrf_token = client.cookies.get(csrf_name)
    assert csrf_token
    cookie_headers = login.headers.get_list("set-cookie")
    assert any(
        header.startswith(f"{settings.cookie_name}=")
        and f"Max-Age={settings.absolute_timeout_hours * 60 * 60}" in header
        and "HttpOnly" in header
        for header in cookie_headers
    )
    assert any(
        header.startswith(f"{csrf_name}=") and "HttpOnly" not in header
        for header in cookie_headers
    )

    session = client.get("/api/v1/auth/session")
    assert session.status_code == 200
    assert session.json()["username"] == "local-admin"
    assert client.get("/api/v1/basemaps").status_code == 200

    missing_csrf = client.post("/api/v1/auth/renew")
    assert missing_csrf.status_code == 403

    previous_session = client.cookies.get(settings.cookie_name)
    renewed = client.post(
        "/api/v1/auth/renew",
        headers={"X-WOMAP-CSRF": csrf_token},
    )
    assert renewed.status_code == 200
    assert client.cookies.get(settings.cookie_name) != previous_session

    renewed_csrf = client.cookies.get(csrf_name)
    logged_out = client.post(
        "/api/v1/auth/logout",
        headers={"X-WOMAP-CSRF": renewed_csrf},
    )
    assert logged_out.status_code == 204
    assert client.get("/api/v1/auth/session").status_code == 401

    async def stored_sessions() -> list[AuthSession]:
        async with session_factory() as database_session:
            result = await database_session.execute(select(AuthSession))
            return list(result.scalars())

    records = asyncio.run(stored_sessions())
    assert len(records) == 2
    assert all(record.revoked_at is not None for record in records)
    assert all(record.token_hash != previous_session for record in records)
    assert all(record.csrf_hash != csrf_token for record in records)


def test_first_run_setup_configures_credential_and_issues_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = RecordingCredentialWriter()
    client, _ = _auth_client(
        tmp_path / "setup-auth.sqlite3",
        monkeypatch,
        credential_configured=False,
        credential_writer=writer,
    )
    origin = get_settings().server.cors_origins[0]

    response = client.post(
        "/api/v1/auth/setup",
        headers={"Origin": origin},
        json={
            "username": "local-admin",
            "password": TEST_PASSWORD,
            "password_confirmation": TEST_PASSWORD,
            "session_mode": "short",
        },
    )

    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert TEST_PASSWORD not in response.text
    assert writer.calls == [("local-admin", TEST_PASSWORD)]
    assert client.cookies.get(get_settings().auth.session.cookie_name)


@pytest.mark.parametrize(
    ("client_host", "origin", "status_code", "detail"),
    [
        ("192.0.2.10", None, 403, "首次设置本地密码只能在本机完成。"),
        ("127.0.0.1", "https://attacker.invalid", 403, "请求来源不受信任。"),
    ],
)
def test_first_run_setup_rejects_nonlocal_or_untrusted_requests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    client_host: str,
    origin: str | None,
    status_code: int,
    detail: str,
) -> None:
    writer = RecordingCredentialWriter()
    client, _ = _auth_client(
        tmp_path / f"blocked-{client_host.replace('.', '-')}.sqlite3",
        monkeypatch,
        credential_configured=False,
        credential_writer=writer,
        client_host=client_host,
    )
    headers = {"Origin": origin} if origin else {}

    response = client.post(
        "/api/v1/auth/setup",
        headers=headers,
        json={
            "username": "local-admin",
            "password": TEST_PASSWORD,
            "password_confirmation": TEST_PASSWORD,
            "session_mode": "short",
        },
    )

    assert response.status_code == status_code
    assert response.json()["detail"] == detail
    assert writer.calls == []


@pytest.mark.parametrize(
    ("username", "confirmation", "status_code"),
    [
        ("wrong-user", TEST_PASSWORD, 401),
        ("local-admin", "different secure password", 400),
    ],
)
def test_first_run_setup_validates_account_and_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    username: str,
    confirmation: str,
    status_code: int,
) -> None:
    writer = RecordingCredentialWriter()
    client, _ = _auth_client(
        tmp_path / f"invalid-setup-{status_code}.sqlite3",
        monkeypatch,
        credential_configured=False,
        credential_writer=writer,
    )

    response = client.post(
        "/api/v1/auth/setup",
        json={
            "username": username,
            "password": TEST_PASSWORD,
            "password_confirmation": confirmation,
            "session_mode": "short",
        },
    )

    assert response.status_code == status_code
    assert writer.calls == []
    assert TEST_PASSWORD not in response.text


def test_first_run_setup_rejects_common_password(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = RecordingCredentialWriter()
    client, _ = _auth_client(
        tmp_path / "common-password.sqlite3",
        monkeypatch,
        credential_configured=False,
        credential_writer=writer,
    )
    common_password = "passwordpassword"

    response = client.post(
        "/api/v1/auth/setup",
        json={
            "username": "local-admin",
            "password": common_password,
            "password_confirmation": common_password,
            "session_mode": "short",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "该密码过于常见，请使用更难猜测的密码。"
    assert writer.calls == []
    assert common_password not in response.text


@pytest.mark.parametrize(
    ("credential_configured", "writer_error", "status_code"),
    [
        (True, None, 409),
        (False, AuthCredentialAlreadyConfiguredError(), 409),
        (False, AuthCredentialWriteError("无法保存本地登录凭据。"), 503),
    ],
)
def test_first_run_setup_handles_repeated_or_failed_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    credential_configured: bool,
    writer_error: Exception | None,
    status_code: int,
) -> None:
    writer = RecordingCredentialWriter(writer_error)
    client, _ = _auth_client(
        tmp_path / f"repeat-setup-{status_code}-{credential_configured}.sqlite3",
        monkeypatch,
        credential_configured=credential_configured,
        credential_writer=writer,
    )

    response = client.post(
        "/api/v1/auth/setup",
        json={
            "username": "local-admin",
            "password": TEST_PASSWORD,
            "password_confirmation": TEST_PASSWORD,
            "session_mode": "short",
        },
    )

    assert response.status_code == status_code
    assert "password_hash" not in response.text
    assert TEST_PASSWORD not in response.text


def test_invalid_credentials_do_not_set_auth_cookies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _auth_client(tmp_path / "invalid-auth.sqlite3", monkeypatch)

    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": "local-admin",
            "password": "definitely wrong password",
            "session_mode": "short",
        },
    )

    assert response.status_code == 401
    assert "set-cookie" not in response.headers


def test_long_session_cookie_uses_remember_me_absolute_lifetime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _auth_client(tmp_path / "long-auth.sqlite3", monkeypatch)
    settings = get_settings().auth.session

    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": "local-admin",
            "password": TEST_PASSWORD,
            "session_mode": "long",
        },
    )

    assert response.status_code == 200
    expected_max_age = settings.remember_me_days * 24 * 60 * 60
    assert any(
        header.startswith(f"{settings.cookie_name}=")
        and f"Max-Age={expected_max_age}" in header
        for header in response.headers.get_list("set-cookie")
    )


def test_login_throttle_resets_after_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _auth_client(tmp_path / "throttle-auth.sqlite3", monkeypatch)
    monkeypatch.setattr(get_settings().auth.throttling, "lockout_attempts", 2)
    invalid_payload = {
        "username": "attacker-one",
        "password": "definitely wrong password",
        "session_mode": "short",
    }

    assert client.post("/api/v1/auth/login", json=invalid_payload).status_code == 401
    successful = client.post(
        "/api/v1/auth/login",
        json={
            "username": "local-admin",
            "password": TEST_PASSWORD,
            "session_mode": "short",
        },
    )
    assert successful.status_code == 200
    assert client.post("/api/v1/auth/login", json=invalid_payload).status_code == 401
    changed_username = {**invalid_payload, "username": "attacker-two"}
    assert client.post("/api/v1/auth/login", json=changed_username).status_code == 401
    changed_again = {**invalid_payload, "username": "attacker-three"}
    assert client.post("/api/v1/auth/login", json=changed_again).status_code == 429


def test_csrf_rejects_untrusted_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _auth_client(tmp_path / "origin-auth.sqlite3", monkeypatch)
    settings = get_settings().auth.session
    login = client.post(
        "/api/v1/auth/login",
        json={
            "username": "local-admin",
            "password": TEST_PASSWORD,
            "session_mode": "short",
        },
    )
    assert login.status_code == 200

    response = client.post(
        "/api/v1/auth/renew",
        headers={
            "Origin": "https://attacker.invalid",
            "X-WOMAP-CSRF": client.cookies.get(csrf_cookie_name(settings)),
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "请求来源不受信任。"
    assert response.json()["request_id"] == response.headers["x-request-id"]
