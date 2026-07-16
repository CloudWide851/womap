from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

from app.features.auth.credentials import (
    AuthCredentialAlreadyConfiguredError,
    AuthCredentialWriteError,
    LocalAuthCredentialWriter,
    hash_password,
    verify_password,
)

TEST_PASSWORD = "correct horse battery staple"


def _fallback(path: Path) -> Path:
    path.write_text(
        "server:\n  port: 8123\nauth:\n  local_user:\n    username: local-admin\n"
        "    password_hash: replace-with-local-hash\nimports:\n  batch_size: 3456\n",
        encoding="utf-8",
    )
    return path


def test_local_auth_credential_writer_preserves_config_and_never_stores_raw_password(
    tmp_path: Path,
) -> None:
    local_path = tmp_path / "settings.local.yaml"
    fallback_path = _fallback(tmp_path / "settings.example.yaml")

    LocalAuthCredentialWriter(local_path, fallback_path).configure("local-admin", TEST_PASSWORD)

    text = local_path.read_text(encoding="utf-8")
    config = yaml.safe_load(text)
    stored_hash = config["auth"]["local_user"]["password_hash"]
    assert config["server"]["port"] == 8123
    assert config["imports"]["batch_size"] == 3456
    assert config["auth"]["local_user"]["password_hash_algorithm"] == "pbkdf2_sha256"
    assert stored_hash.startswith("pbkdf2_sha256$600000$")
    assert verify_password(TEST_PASSWORD, stored_hash)
    assert TEST_PASSWORD not in text
    assert "replace-with-local-hash" in fallback_path.read_text(encoding="utf-8")


def test_password_hashes_use_unique_salts_and_reject_other_passwords() -> None:
    first = hash_password(TEST_PASSWORD)
    second = hash_password(TEST_PASSWORD)

    assert first != second
    assert verify_password(TEST_PASSWORD, first)
    assert not verify_password("different secure password", first)


def test_local_auth_credential_writer_allows_only_one_concurrent_setup(tmp_path: Path) -> None:
    local_path = tmp_path / "settings.local.yaml"
    writer = LocalAuthCredentialWriter(local_path, _fallback(tmp_path / "settings.example.yaml"))

    def configure() -> str:
        try:
            writer.configure("local-admin", TEST_PASSWORD)
        except AuthCredentialAlreadyConfiguredError:
            return "conflict"
        return "configured"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: configure(), range(2)))

    assert sorted(results) == ["configured", "conflict"]


def test_local_auth_credential_writer_returns_redacted_write_error(tmp_path: Path) -> None:
    blocked_parent = tmp_path / "blocked"
    blocked_parent.write_text("not a directory", encoding="utf-8")
    writer = LocalAuthCredentialWriter(
        blocked_parent / "settings.local.yaml",
        _fallback(tmp_path / "settings.example.yaml"),
    )

    with pytest.raises(AuthCredentialWriteError, match="无法保存本地登录凭据") as error:
        writer.configure("local-admin", TEST_PASSWORD)

    assert str(blocked_parent) not in str(error.value)
