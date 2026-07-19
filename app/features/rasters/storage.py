from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.shared.config import ROOT_DIR


class RasterStorageError(ValueError):
    pass


@dataclass(frozen=True)
class RasterSpaceEstimate:
    source_bytes: int
    candidate_asset_bytes: int
    formula_intermediate_bytes: int
    compression_overview_bytes: int
    final_asset_bytes: int
    scratch_required_bytes: int
    store_required_bytes: int
    reserve_bytes: int

    def public_summary(self) -> dict[str, int]:
        return {
            "source": self.source_bytes,
            "candidate_asset": self.candidate_asset_bytes,
            "formula_intermediate": self.formula_intermediate_bytes,
            "compression_overview": self.compression_overview_bytes,
            "final_asset": self.final_asset_bytes,
            "scratch_required": self.scratch_required_bytes,
            "store_required": self.store_required_bytes,
            "reserve": self.reserve_bytes,
        }


class RasterStorage:
    def __init__(self, store_path: str, scratch_path: str, quota_gb: int) -> None:
        self.root = self._resolve(store_path)
        self.scratch = self._resolve(scratch_path)
        if self.root == self.scratch or self.root in self.scratch.parents or self.scratch in self.root.parents:
            raise RasterStorageError("栅格存储目录和临时目录必须相互独立。")
        self.quota_bytes = int(quota_gb) * 1024**3
        self.root.mkdir(parents=True, exist_ok=True)
        self.scratch.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _resolve(value: str) -> Path:
        path = Path(value).expanduser()
        return path.resolve() if path.is_absolute() else (ROOT_DIR / path).resolve()

    @staticmethod
    def display_path(path: Path) -> str:
        try:
            return path.relative_to(ROOT_DIR).as_posix()
        except ValueError:
            return path.name

    def assert_managed(self, path: str | Path) -> Path:
        resolved = Path(path).resolve()
        if resolved == self.root or self.root not in resolved.parents:
            raise RasterStorageError("栅格资产不在托管目录内。")
        return resolved

    def usage_bytes(self) -> int:
        return sum(path.stat().st_size for path in self.root.rglob("*") if path.is_file())

    def scratch_bytes(self) -> int:
        return sum(path.stat().st_size for path in self.scratch.rglob("*") if path.is_file())

    def asset_paths(self) -> set[Path]:
        return {path.resolve() for path in self.root.rglob("*.tif") if path.is_file()}

    def preflight(
        self,
        source_bytes: int,
        replacing_bytes: int = 0,
        *,
        operation: Literal["convert", "formula"] = "convert",
        reserve_bytes: int = 0,
    ) -> RasterSpaceEstimate:
        source_bytes = max(0, int(source_bytes))
        minimum_asset = 64 * 1024**2
        final_asset = max(minimum_asset, int(source_bytes * 1.10))
        candidate_asset = final_asset
        formula_intermediate = final_asset if operation == "formula" else 0
        compression_overview = max(32 * 1024**2, int(final_asset * 0.35))
        scratch_required = candidate_asset + formula_intermediate + compression_overview
        store_required = final_asset
        reserve_bytes = max(0, int(reserve_bytes))
        estimate = RasterSpaceEstimate(
            source_bytes=source_bytes,
            candidate_asset_bytes=candidate_asset,
            formula_intermediate_bytes=formula_intermediate,
            compression_overview_bytes=compression_overview,
            final_asset_bytes=final_asset,
            scratch_required_bytes=scratch_required,
            store_required_bytes=store_required,
            reserve_bytes=reserve_bytes,
        )
        projected = self.usage_bytes() - max(0, replacing_bytes) + store_required
        if projected > self.quota_bytes:
            raise RasterStorageError("栅格存储配额不足，请清理孤儿资产或提高配额。")
        if shutil.disk_usage(self.scratch).free < scratch_required + reserve_bytes:
            raise RasterStorageError("临时目录磁盘空间不足，无法安全转换栅格。")
        if shutil.disk_usage(self.root).free < store_required + reserve_bytes:
            raise RasterStorageError("栅格存储磁盘空间不足。")
        return estimate

    def cleanup_orphans(self, referenced: set[Path]) -> tuple[int, int]:
        referenced = {path.resolve() for path in referenced}
        deleted = 0
        freed = 0
        for path in sorted(self.asset_paths() - referenced):
            size = path.stat().st_size
            path.unlink(missing_ok=True)
            deleted += 1
            freed += size
        for path in self.scratch.rglob("*"):
            if not path.is_file():
                continue
            size = path.stat().st_size
            path.unlink(missing_ok=True)
            deleted += 1
            freed += size
        return deleted, freed
