from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from pathlib import Path
from threading import Lock
from typing import Any, Protocol

import yaml

from app.shared.config import (
    EXAMPLE_CONFIG_PATH,
    LOCAL_CONFIG_PATH,
    get_settings,
    is_password_hash_configured,
)

PBKDF2_ITERATIONS = 600_000
_credential_write_lock = Lock()


class AuthCredentialAlreadyConfiguredError(RuntimeError):
    pass


class AuthCredentialWriteError(RuntimeError):
    pass


class AuthCredentialWriterProtocol(Protocol):
    def configure(self, username: str, password: str) -> None: ...


def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_urlsafe(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    encoded = base64.b64encode(digest).decode("ascii").rstrip("=")
    return f"pbkdf2_sha256${iterations}${salt}${encoded}"


def verify_password(password: str, encoded_hash: str) -> bool:
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


class LocalAuthCredentialWriter:
    def __init__(
        self,
        local_config_path: Path = LOCAL_CONFIG_PATH,
        fallback_config_path: Path = EXAMPLE_CONFIG_PATH,
    ) -> None:
        self.local_config_path = local_config_path
        self.fallback_config_path = fallback_config_path

    def configure(self, username: str, password: str) -> None:
        with _credential_write_lock:
            raw_config = self._read_edit_base()
            auth_config = self._ensure_mapping(raw_config, "auth")
            local_user = self._ensure_mapping(auth_config, "local_user")
            existing_hash = str(local_user.get("password_hash", ""))
            if is_password_hash_configured(existing_hash):
                raise AuthCredentialAlreadyConfiguredError

            local_user["username"] = username
            local_user["password_hash"] = hash_password(password)
            local_user["password_hash_algorithm"] = "pbkdf2_sha256"
            self._write_local_config(raw_config)

    def _read_edit_base(self) -> dict[str, Any]:
        config_path = (
            self.local_config_path
            if self.local_config_path.exists()
            else self.fallback_config_path
        )
        if not config_path.exists():
            return {}
        try:
            with config_path.open("r", encoding="utf-8") as config_file:
                loaded = yaml.safe_load(config_file) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise AuthCredentialWriteError("无法读取本地登录配置。") from exc
        return loaded if isinstance(loaded, dict) else {}

    def _write_local_config(self, raw_config: dict[str, Any]) -> None:
        temporary_path = self.local_config_path.with_suffix(".tmp")
        try:
            self.local_config_path.parent.mkdir(parents=True, exist_ok=True)
            with temporary_path.open("w", encoding="utf-8") as config_file:
                yaml.safe_dump(raw_config, config_file, allow_unicode=True, sort_keys=False)
            temporary_path.replace(self.local_config_path)
        except OSError as exc:
            temporary_path.unlink(missing_ok=True)
            raise AuthCredentialWriteError("无法保存本地登录凭据。") from exc
        get_settings.cache_clear()

    @staticmethod
    def _ensure_mapping(config: dict[str, Any], key: str) -> dict[str, Any]:
        section = config.get(key)
        if not isinstance(section, dict):
            section = {}
            config[key] = section
        return section
