from pathlib import Path, PureWindowsPath
import logging
from typing import Any
from uuid import uuid4

import yaml

from app.features.settings.schemas import (
    ImportOptionsUpdate,
    ImportSettingsResponse,
    ImportSourceCreate,
    ImportSourceResponse,
    ImportSourceTestResponse,
    ImportSourceUpdate,
    LocalFrontendDevServerSettings,
    LocalFrontendSettings,
    LocalRuntimeSettings,
    LocalRuntimeSettingsUpdate,
    LocalServerSettings,
    RuntimeAuthSettings,
    RuntimePerformanceSettings,
    RuntimeSettings,
)
from app.features.settings.credentials import (
    CredentialStore,
    CredentialStoreError,
    CredentialStoreProtocol,
)
from app.shared.config import EXAMPLE_CONFIG_PATH, LOCAL_CONFIG_PATH, get_settings, load_settings

logger = logging.getLogger("womap.settings")


def _config_source_label(config_source: str) -> str:
    try:
        resolved = Path(config_source).resolve()
    except OSError:
        return "unknown"
    if resolved == LOCAL_CONFIG_PATH.resolve():
        return "local"
    if resolved == EXAMPLE_CONFIG_PATH.resolve():
        return "example"
    return "unknown"


class SettingsService:
    def __init__(
        self,
        local_config_path: Path = LOCAL_CONFIG_PATH,
        fallback_config_path: Path = EXAMPLE_CONFIG_PATH,
        credential_store: CredentialStoreProtocol | None = None,
    ) -> None:
        self.local_config_path = local_config_path
        self.fallback_config_path = fallback_config_path
        self.credential_store = credential_store or CredentialStore()

    async def get_runtime_settings(self) -> RuntimeSettings:
        settings = get_settings()
        performance = settings.performance
        auth = settings.auth
        return RuntimeSettings(
            environment=settings.app.environment,
            config_source=_config_source_label(settings.config_source),
            database=settings.database.kind,
            postgis_target=settings.database.uses_postgis,
            redis_configured=settings.redis.configured,
            auth=RuntimeAuthSettings(
                enabled=auth.enabled,
                credential_configured=auth.local_user.password_configured,
                password_min_length=auth.password_policy.min_length,
                password_max_length=auth.password_policy.max_length,
                idle_timeout_minutes=auth.session.idle_timeout_minutes,
                absolute_timeout_hours=auth.session.absolute_timeout_hours,
                renewal_timeout_minutes=auth.session.renewal_timeout_minutes,
                remember_me_days=auth.session.remember_me_days,
                policy_refresh_seconds=auth.dynamic_update.policy_refresh_seconds,
                warn_before_expire_minutes=auth.dynamic_update.warn_before_expire_minutes,
            ),
            performance=RuntimePerformanceSettings(
                profile=performance.profile,
                max_features_per_request=performance.max_features_per_request,
                default_bbox_limit=performance.default_bbox_limit,
                simplify_tolerance=performance.simplify_tolerance,
                cache_ttl_seconds=performance.cache_ttl_seconds,
                large_layer_feature_threshold=performance.large_layer_feature_threshold,
                tile_feature_threshold=performance.tile_feature_threshold,
            ),
            panel_defaults={
                "layers": True,
                "basemaps": True,
                "jobs": True,
                "properties": True,
                "fields": True,
                "performance": True,
            },
        )

    async def get_local_runtime_settings(self) -> LocalRuntimeSettings:
        config_path = (
            self.local_config_path if self.local_config_path.exists() else self.fallback_config_path
        )
        settings = load_settings(config_path)
        return LocalRuntimeSettings(
            config_source="local" if config_path == self.local_config_path else "example",
            local_config_path="config/settings.local.yaml",
            server=LocalServerSettings(host=settings.server.host, port=settings.server.port),
            frontend=LocalFrontendSettings(
                dev_server=LocalFrontendDevServerSettings(
                    host=settings.frontend.dev_server.host,
                    port=settings.frontend.dev_server.port,
                ),
            ),
        )

    async def update_local_runtime_settings(
        self, payload: LocalRuntimeSettingsUpdate
    ) -> LocalRuntimeSettings:
        raw_config = self._read_edit_base()
        server_config = self._ensure_mapping(raw_config, "server")
        frontend_config = self._ensure_mapping(raw_config, "frontend")
        dev_server_config = self._ensure_mapping(frontend_config, "dev_server")

        server_config["host"] = payload.server.host
        server_config["port"] = payload.server.port
        dev_server_config["host"] = payload.frontend.dev_server.host
        dev_server_config["port"] = payload.frontend.dev_server.port

        self.local_config_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.local_config_path.with_suffix(".tmp")
        with temporary_path.open("w", encoding="utf-8") as config_file:
            yaml.safe_dump(raw_config, config_file, allow_unicode=True, sort_keys=False)
        temporary_path.replace(self.local_config_path)
        get_settings.cache_clear()
        return await self.get_local_runtime_settings()

    async def get_import_settings(self) -> ImportSettingsResponse:
        settings = load_settings(
            self.local_config_path if self.local_config_path.exists() else self.fallback_config_path
        ).imports
        return ImportSettingsResponse(
            cache_path=settings.cache_path,
            batch_size=settings.batch_size,
            raster_store_path=settings.raster_store_path,
            raster_scratch_path=settings.raster_scratch_path,
            raster_quota_gb=settings.raster_quota_gb,
            sources=[self._source_response(source.model_dump()) for source in settings.sources],
        )

    async def create_import_source(self, payload: ImportSourceCreate) -> ImportSourceResponse:
        self._validate_import_source(payload)
        source_id = uuid4().hex[:12]
        source = payload.model_dump(exclude={"password"}) | {"id": source_id}
        raw_config = self._read_edit_base()
        imports_config = self._ensure_mapping(raw_config, "imports")
        sources = imports_config.setdefault("sources", [])
        if not isinstance(sources, list):
            sources = []
            imports_config["sources"] = sources
        sources.append(source)
        self._write_local_config(raw_config)
        if payload.kind == "smb" and payload.password:
            self.credential_store.set_password(source_id, self._credential_username(source), payload.password)
        return self._source_response(source)

    async def update_import_source(
        self, source_id: str, payload: ImportSourceUpdate
    ) -> ImportSourceResponse:
        self._validate_import_source(payload)
        raw_config = self._read_edit_base()
        sources = self._raw_import_sources(raw_config)
        index = next((i for i, source in enumerate(sources) if source.get("id") == source_id), -1)
        if index < 0:
            raise KeyError(source_id)
        previous = dict(sources[index])
        source = payload.model_dump(exclude={"password"}) | {"id": source_id}
        sources[index] = source
        self._write_local_config(raw_config)
        old_username = self._credential_username(previous)
        new_username = self._credential_username(source)
        if old_username != new_username:
            try:
                self.credential_store.delete_password(source_id, old_username)
            except CredentialStoreError:
                pass
        if payload.kind == "smb" and payload.password:
            self.credential_store.set_password(source_id, new_username, payload.password)
        return self._source_response(source)

    async def delete_import_source(self, source_id: str) -> None:
        raw_config = self._read_edit_base()
        sources = self._raw_import_sources(raw_config)
        source = next((item for item in sources if item.get("id") == source_id), None)
        if source is None:
            raise KeyError(source_id)
        sources.remove(source)
        self._write_local_config(raw_config)
        if source.get("kind") == "smb":
            try:
                self.credential_store.delete_password(
                    source_id, self._credential_username(source)
                )
            except CredentialStoreError:
                pass

    async def update_import_options(self, payload: ImportOptionsUpdate) -> ImportSettingsResponse:
        raw_config = self._read_edit_base()
        imports_config = self._ensure_mapping(raw_config, "imports")
        imports_config["cache_path"] = payload.cache_path.strip()
        imports_config["batch_size"] = payload.batch_size
        imports_config["raster_store_path"] = payload.raster_store_path.strip()
        imports_config["raster_scratch_path"] = payload.raster_scratch_path.strip()
        imports_config["raster_quota_gb"] = payload.raster_quota_gb
        self._write_local_config(raw_config)
        return await self.get_import_settings()

    async def test_import_source(
        self, source_id: str, password: str | None = None
    ) -> ImportSourceTestResponse:
        settings = await self.get_import_settings()
        source = next((item for item in settings.sources if item.id == source_id), None)
        if source is None:
            raise KeyError(source_id)
        if source.kind == "local":
            root = Path(source.root_path).expanduser()
            if not root.is_dir():
                raise ValueError("本地数据目录不存在或不可访问。")
            return ImportSourceTestResponse(ok=True, message="本地目录可访问。")

        credential = password or self.credential_store.get_password(
            source.id, self._credential_username(source.model_dump())
        )
        if not credential:
            raise ValueError("SMB 密码尚未配置，请在设置中保存密码。")
        try:
            import smbclient

            root = self._smb_root(source.model_dump())
            smbclient.register_session(
                source.server,
                username=self._credential_username(source.model_dump()),
                password=credential,
                port=source.port,
                encrypt=source.encrypt,
            )
            list(smbclient.scandir(root))
        except Exception as exc:
            logger.warning(
                "import_source_test_failed source_id=%s error_type=%s",
                source.id,
                type(exc).__name__,
            )
            raise ValueError("SMB 连接失败，请检查地址、网络和凭据。") from exc
        return ImportSourceTestResponse(ok=True, message="SMB 连接成功。")

    def _read_edit_base(self) -> dict[str, Any]:
        config_path = (
            self.local_config_path if self.local_config_path.exists() else self.fallback_config_path
        )
        if not config_path.exists():
            return {}
        with config_path.open("r", encoding="utf-8") as config_file:
            loaded_config = yaml.safe_load(config_file) or {}
        if not isinstance(loaded_config, dict):
            return {}
        return loaded_config

    def _write_local_config(self, raw_config: dict[str, Any]) -> None:
        self.local_config_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.local_config_path.with_suffix(".tmp")
        with temporary_path.open("w", encoding="utf-8") as config_file:
            yaml.safe_dump(raw_config, config_file, allow_unicode=True, sort_keys=False)
        temporary_path.replace(self.local_config_path)
        get_settings.cache_clear()

    def _raw_import_sources(self, raw_config: dict[str, Any]) -> list[dict[str, Any]]:
        imports_config = self._ensure_mapping(raw_config, "imports")
        sources = imports_config.setdefault("sources", [])
        if not isinstance(sources, list):
            sources = []
        normalized_sources = [source for source in sources if isinstance(source, dict)]
        imports_config["sources"] = normalized_sources
        return normalized_sources

    def _source_response(self, source: dict[str, Any]) -> ImportSourceResponse:
        configured = False
        if source.get("kind") == "smb" and source.get("username"):
            try:
                configured = bool(
                    self.credential_store.get_password(
                        str(source.get("id", "")), self._credential_username(source)
                    )
                )
            except CredentialStoreError:
                configured = False
        return ImportSourceResponse.model_validate(source | {"credential_configured": configured})

    @staticmethod
    def _validate_import_source(payload: ImportSourceCreate | ImportSourceUpdate) -> None:
        if payload.kind == "local" and not payload.root_path:
            raise ValueError("本地数据源必须配置根目录。")
        if payload.kind == "smb" and not (payload.server and payload.share and payload.username):
            raise ValueError("SMB 数据源必须配置服务器、共享名和用户名。")

    @staticmethod
    def _credential_username(source: dict[str, Any]) -> str:
        username = str(source.get("username", ""))
        domain = str(source.get("domain", ""))
        return f"{domain}\\{username}" if domain else username

    @staticmethod
    def _smb_root(source: dict[str, Any]) -> str:
        root = PureWindowsPath(
            "\\\\",
            str(source.get("server", "")),
            str(source.get("share", "")),
            str(source.get("base_path", "")),
        )
        return str(root)

    @staticmethod
    def _ensure_mapping(config: dict[str, Any], key: str) -> dict[str, Any]:
        section = config.get(key)
        if not isinstance(section, dict):
            section = {}
            config[key] = section
        return section
