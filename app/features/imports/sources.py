from __future__ import annotations

import json
import ntpath
import os
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from threading import Lock

from app.features.settings.credentials import CredentialStore, CredentialStoreProtocol
from app.features.settings.schemas import ImportSourceResponse

RELEVANT_SOURCE_SUFFIXES = {
    ".shp",
    ".shx",
    ".dbf",
    ".prj",
    ".cpg",
    ".sbn",
    ".sbx",
    ".xml",
    ".tif",
    ".tiff",
    ".img",
    ".jp2",
    ".j2k",
    ".vrt",
    ".hdf",
    ".h4",
    ".h5",
    ".he5",
    ".nc",
    ".nc4",
    ".cdf",
}


@dataclass
class TransferProgress:
    copied_bytes: int = 0
    total_bytes: int = 0
    current_file: str = ""

    def __post_init__(self) -> None:
        self._lock = Lock()

    def update(self, copied_bytes: int, total_bytes: int, current_file: str) -> None:
        with self._lock:
            self.copied_bytes = copied_bytes
            self.total_bytes = total_bytes
            self.current_file = current_file

    def snapshot(self) -> tuple[int, int, str]:
        with self._lock:
            return self.copied_bytes, self.total_bytes, self.current_file


class SourceMaterializer:
    def __init__(self, credential_store: CredentialStoreProtocol | None = None) -> None:
        self.credential_store = credential_store or CredentialStore()

    def materialize(
        self,
        source: ImportSourceResponse,
        cache_root: Path,
        progress: TransferProgress | None = None,
    ) -> Path:
        if source.kind == "local":
            root = Path(source.root_path).expanduser().resolve()
            if not root.is_dir():
                raise ValueError("本地数据目录不存在或不可访问。")
            return root
        return self._materialize_smb(source, cache_root, progress or TransferProgress())

    def test(self, source: ImportSourceResponse) -> None:
        if source.kind == "local":
            if not Path(source.root_path).expanduser().is_dir():
                raise ValueError("本地数据目录不存在或不可访问。")
            return
        import smbclient

        password = self._password(source)
        smbclient.register_session(
            source.server,
            username=self._username(source),
            password=password,
            port=source.port,
            encrypt=source.encrypt,
        )
        list(smbclient.scandir(self._smb_root(source)))

    def _materialize_smb(
        self, source: ImportSourceResponse, cache_root: Path, progress: TransferProgress
    ) -> Path:
        import smbclient

        password = self._password(source)
        smbclient.register_session(
            source.server,
            username=self._username(source),
            password=password,
            port=source.port,
            encrypt=source.encrypt,
        )
        remote_root = self._smb_root(source)
        target_root = (cache_root / source.id / "source").resolve()
        target_root.mkdir(parents=True, exist_ok=True)
        manifest_path = target_root.parent / "transfer-manifest.json"
        manifest = self._read_manifest(manifest_path)
        remote_files: list[tuple[str, str, int, int]] = []
        total_bytes = 0

        for current, _, names in smbclient.walk(remote_root):
            inside_gdb = any(part.lower().endswith(".gdb") for part in PureWindowsPath(current).parts)
            for name in names:
                suffix = Path(name).suffix.lower()
                if not inside_gdb and suffix not in RELEVANT_SOURCE_SUFFIXES:
                    continue
                remote_path = ntpath.join(current, name)
                relative = ntpath.relpath(remote_path, remote_root)
                if relative == ".." or relative.startswith(f"..{ntpath.sep}"):
                    raise ValueError("SMB 数据路径超出配置的共享根目录。")
                stat = smbclient.stat(remote_path)
                size = int(stat.st_size)
                mtime_ns = int(stat.st_mtime_ns)
                remote_files.append((remote_path, relative, size, mtime_ns))
                total_bytes += size

        expected_paths: set[Path] = set()
        for _, relative, _, _ in remote_files:
            local_path = (target_root / Path(*PureWindowsPath(relative).parts)).resolve()
            expected_paths.add(local_path)
            expected_paths.add(local_path.with_suffix(local_path.suffix + ".part"))
        for cached_path in target_root.rglob("*"):
            if cached_path.is_file() and cached_path.resolve() not in expected_paths:
                cached_path.unlink()
        remote_relatives = {relative for _, relative, _, _ in remote_files}
        manifest = {key: value for key, value in manifest.items() if key in remote_relatives}

        completed_bytes = 0
        for remote_path, relative, size, mtime_ns in remote_files:
            local_path = (target_root / Path(*PureWindowsPath(relative).parts)).resolve()
            if target_root not in local_path.parents:
                raise ValueError("SMB 数据路径超出本地缓存目录。")
            local_path.parent.mkdir(parents=True, exist_ok=True)
            item = manifest.get(relative, {})
            if (
                local_path.is_file()
                and local_path.stat().st_size == size
                and item.get("mtime_ns") == mtime_ns
            ):
                completed_bytes += size
                progress.update(completed_bytes, total_bytes, relative)
                continue

            partial = local_path.with_suffix(local_path.suffix + ".part")
            offset = partial.stat().st_size if partial.exists() else 0
            if item.get("size") != size or item.get("mtime_ns") != mtime_ns or offset > size:
                partial.unlink(missing_ok=True)
                offset = 0
            manifest[relative] = {"size": size, "mtime_ns": mtime_ns}
            self._write_manifest(manifest_path, manifest)
            with smbclient.open_file(remote_path, mode="rb") as remote_file:
                remote_file.seek(offset)
                with partial.open("ab") as local_file:
                    copied = offset
                    while copied < size:
                        chunk = remote_file.read(min(4 * 1024 * 1024, size - copied))
                        if not chunk:
                            raise OSError(f"SMB 文件提前结束：{relative}")
                        local_file.write(chunk)
                        copied += len(chunk)
                        progress.update(completed_bytes + copied, total_bytes, relative)
            partial.replace(local_path)
            os.utime(local_path, ns=(mtime_ns, mtime_ns))
            completed_bytes += size
            progress.update(completed_bytes, total_bytes, relative)

        self._write_manifest(manifest_path, manifest)
        return target_root

    def _password(self, source: ImportSourceResponse) -> str:
        password = self.credential_store.get_password(source.id, self._username(source))
        if not password:
            raise ValueError("SMB 密码尚未配置，请前往设置页保存凭据。")
        return password

    @staticmethod
    def _username(source: ImportSourceResponse) -> str:
        return f"{source.domain}\\{source.username}" if source.domain else source.username

    @staticmethod
    def _smb_root(source: ImportSourceResponse) -> str:
        root = f"\\\\{source.server}\\{source.share}"
        if source.base_path:
            root = ntpath.join(root, source.base_path.strip("\\/"))
        return root

    @staticmethod
    def _read_manifest(path: Path) -> dict[str, dict[str, int]]:
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _write_manifest(path: Path, manifest: dict[str, dict[str, int]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
