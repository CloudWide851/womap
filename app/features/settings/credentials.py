from __future__ import annotations

from typing import Protocol


class CredentialStoreError(RuntimeError):
    pass


class CredentialStoreProtocol(Protocol):
    def get_password(self, source_id: str, username: str) -> str | None: ...

    def set_password(self, source_id: str, username: str, password: str) -> None: ...

    def delete_password(self, source_id: str, username: str) -> None: ...


class CredentialStore:
    service_prefix = "WOMAP/import-source"

    def _service_name(self, source_id: str) -> str:
        return f"{self.service_prefix}/{source_id}"

    def get_password(self, source_id: str, username: str) -> str | None:
        try:
            import keyring

            return keyring.get_password(self._service_name(source_id), username)
        except Exception as exc:
            raise CredentialStoreError("Windows 凭据库不可用，请检查 keyring 后端。") from exc

    def set_password(self, source_id: str, username: str, password: str) -> None:
        try:
            import keyring

            keyring.set_password(self._service_name(source_id), username, password)
        except Exception as exc:
            raise CredentialStoreError("无法写入 Windows 凭据库。") from exc

    def delete_password(self, source_id: str, username: str) -> None:
        try:
            import keyring
            from keyring.errors import PasswordDeleteError

            try:
                keyring.delete_password(self._service_name(source_id), username)
            except PasswordDeleteError:
                return
        except Exception as exc:
            raise CredentialStoreError("无法删除 Windows 凭据库中的连接密码。") from exc
