from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from app.features.rasters.schemas import FormulaNode
from app.features.rasters.storage import RasterStorage
from app.shared.gdal import configure_bundled_gdal


configure_bundled_gdal()

ProgressCallback = Callable[[str, int, int], None]


class RasterProcessor:
    def __init__(self, storage: RasterStorage) -> None:
        self.storage = storage

    def to_cog(
        self,
        source_uri: str,
        *,
        dataset_id: str,
        fingerprint: str,
        source_crs: str | None = None,
        progress: ProgressCallback | None = None,
    ) -> tuple[Path, dict, dict[str, float]]:
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.shutil import copy as rio_copy
        from rasterio.vrt import WarpedVRT

        source_path = self._physical_source_path(source_uri)
        source_bytes = source_path.stat().st_size
        self.storage.preflight(source_bytes)
        final_path = self.storage.root / f"{dataset_id}-{fingerprint[:16]}.tif"
        temporary = self.storage.scratch / f"{dataset_id}-{uuid4().hex}.tif"
        if progress:
            progress("converting", 0, source_bytes)
        try:
            with rasterio.Env(GDAL_CACHEMAX=256, GDAL_NUM_THREADS="ALL_CPUS"):
                with rasterio.open(source_uri) as source:
                    source_crs_value = source.crs or source_crs
                    if source_crs_value is None:
                        raise ValueError("栅格缺少 CRS，请提供 EPSG 覆盖值。")
                    resampling = (
                        Resampling.bilinear
                        if any(dtype.startswith(("float", "uint8", "uint16")) for dtype in source.dtypes)
                        else Resampling.nearest
                    )
                    with WarpedVRT(
                        source,
                        src_crs=source_crs_value,
                        crs="EPSG:3857",
                        resampling=resampling,
                    ) as warped:
                        rio_copy(
                            warped,
                            temporary,
                            driver="COG",
                            BLOCKSIZE=512,
                            BIGTIFF="YES",
                            COMPRESS="DEFLATE",
                            PREDICTOR="YES",
                            OVERVIEWS="AUTO",
                            NUM_THREADS="ALL_CPUS",
                        )
            metadata, bounds = self.inspect(temporary)
            temporary.replace(final_path)
            if progress:
                progress("completed", source_bytes, source_bytes)
            return final_path, metadata, bounds
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def materialize_formula(
        self,
        source_path: Path,
        destination_id: str,
        fingerprint: str,
        formula: FormulaNode,
        progress: ProgressCallback | None = None,
    ) -> tuple[Path, dict, dict[str, float]]:
        import numpy as np
        import rasterio
        from rasterio.shutil import copy as rio_copy

        self.validate_formula(formula)
        source_path = self.storage.assert_managed(source_path)
        self.storage.preflight(source_path.stat().st_size)
        intermediate = self.storage.scratch / f"formula-{uuid4().hex}.tif"
        cog_temp = self.storage.scratch / f"formula-cog-{uuid4().hex}.tif"
        final_path = self.storage.root / f"{destination_id}-{fingerprint[:16]}.tif"
        bands = sorted(self.formula_bands(formula))
        try:
            with rasterio.open(source_path) as source:
                if max(bands) > source.count:
                    raise ValueError("公式引用的波段超出当前栅格范围。")
                profile = source.profile.copy()
                profile.update(
                    driver="GTiff",
                    count=1,
                    dtype="float32",
                    nodata=-9999.0,
                    tiled=True,
                    blockxsize=512,
                    blockysize=512,
                    compress="deflate",
                    predictor=3,
                    BIGTIFF="YES",
                )
                windows = list(source.block_windows(1))
                with rasterio.open(intermediate, "w", **profile) as target:
                    for block_index, (_, window) in enumerate(windows, start=1):
                        arrays = source.read(bands, window=window, masked=True).astype("float32")
                        band_values = {band: arrays[index] for index, band in enumerate(bands)}
                        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
                            value = self.evaluate_formula(formula, band_values)
                        mask = np.ma.getmaskarray(value) if np.ma.isMaskedArray(value) else False
                        value_array = np.asarray(value, dtype="float32")
                        invalid = ~np.isfinite(value_array) | mask
                        target.write(
                            np.where(invalid, -9999.0, value_array), 1, window=window
                        )
                        if progress:
                            progress("processing", block_index, len(windows))
            rio_copy(
                intermediate,
                cog_temp,
                driver="COG",
                BLOCKSIZE=512,
                BIGTIFF="YES",
                COMPRESS="DEFLATE",
                PREDICTOR="YES",
                OVERVIEWS="AUTO",
            )
            metadata, bounds = self.inspect(cog_temp)
            cog_temp.replace(final_path)
            return final_path, metadata, bounds
        finally:
            intermediate.unlink(missing_ok=True)
            cog_temp.unlink(missing_ok=True)

    @staticmethod
    def inspect(path: Path) -> tuple[dict, dict[str, float]]:
        import rasterio

        with rasterio.open(path) as dataset:
            if dataset.crs is None or dataset.crs.to_epsg() != 3857:
                raise ValueError("托管栅格没有正确转换为 EPSG:3857。")
            image_structure = dataset.tags(ns="IMAGE_STRUCTURE")
            if image_structure.get("LAYOUT") not in {None, "COG"}:
                raise ValueError("输出文件不是有效的 COG 布局。")
            bands = []
            nodata_values = []
            for index in range(1, dataset.count + 1):
                nodata = dataset.nodatavals[index - 1]
                if nodata is not None and not math.isfinite(float(nodata)):
                    nodata = None
                nodata_values.append(nodata)
                bands.append(
                    {
                        "index": index,
                        "name": dataset.descriptions[index - 1] or f"Band {index}",
                        "dtype": dataset.dtypes[index - 1],
                        "nodata": nodata,
                        "color_interpretation": dataset.colorinterp[index - 1].name,
                    }
                )
            metadata = {
                "width": dataset.width,
                "height": dataset.height,
                "band_count": dataset.count,
                "driver": dataset.driver,
                "dtypes": list(dataset.dtypes),
                "nodata": nodata_values,
                "resolution": [abs(float(dataset.res[0])), abs(float(dataset.res[1]))],
                "byte_size": path.stat().st_size,
                "bands": bands,
                "overviews": dataset.overviews(1) if dataset.count else [],
                "block_shapes": [list(shape) for shape in dataset.block_shapes],
            }
            bounds = {
                "min_x": float(dataset.bounds.left),
                "min_y": float(dataset.bounds.bottom),
                "max_x": float(dataset.bounds.right),
                "max_y": float(dataset.bounds.top),
            }
            return metadata, bounds

    @classmethod
    def validate_formula(cls, formula: FormulaNode, band_count: int = 256) -> None:
        nodes = 0
        function_arity = {"abs": 1, "sqrt": 1, "log": 1, "min": 2, "max": 2, "clamp": 3}

        def walk(node: FormulaNode, depth: int) -> None:
            nonlocal nodes
            nodes += 1
            if nodes > 64 or depth > 12:
                raise ValueError("波段公式过于复杂。")
            if node.kind == "band" and (node.band is None or not 1 <= node.band <= band_count):
                raise ValueError("波段编号超出允许范围。")
            if node.kind == "number" and (
                node.value is None or not math.isfinite(node.value) or abs(node.value) > 1e12
            ):
                raise ValueError("公式常量无效或过大。")
            if node.kind == "function" and len(node.arguments) != function_arity.get(
                str(node.name), 0
            ):
                raise ValueError("公式函数参数数量无效。")
            for child in (node.argument, node.left, node.right):
                if child is not None:
                    walk(child, depth + 1)
            for child in node.arguments:
                walk(child, depth + 1)

        walk(formula, 1)

    @classmethod
    def formula_bands(cls, formula: FormulaNode) -> set[int]:
        result: set[int] = set()
        if formula.kind == "band" and formula.band is not None:
            result.add(formula.band)
        for child in (formula.argument, formula.left, formula.right):
            if child is not None:
                result.update(cls.formula_bands(child))
        for child in formula.arguments:
            result.update(cls.formula_bands(child))
        return result

    @classmethod
    def evaluate_formula(cls, node: FormulaNode, bands: dict[int, object]):
        import numpy as np

        if node.kind == "band":
            return bands[int(node.band or 0)]
        if node.kind == "number":
            return float(node.value or 0)
        if node.kind == "unary":
            value = cls.evaluate_formula(node.argument, bands)  # type: ignore[arg-type]
            return value if node.operator == "+" else -value
        if node.kind == "binary":
            left = cls.evaluate_formula(node.left, bands)  # type: ignore[arg-type]
            right = cls.evaluate_formula(node.right, bands)  # type: ignore[arg-type]
            return {
                "+": lambda: left + right,
                "-": lambda: left - right,
                "*": lambda: left * right,
                "/": lambda: left / right,
                "^": lambda: np.power(left, right),
            }[str(node.operator)]()
        values = [cls.evaluate_formula(argument, bands) for argument in node.arguments]
        if node.name == "abs":
            return np.abs(values[0])
        if node.name == "sqrt":
            return np.sqrt(values[0])
        if node.name == "log":
            return np.log(values[0])
        if node.name == "min":
            return np.minimum(values[0], values[1])
        if node.name == "max":
            return np.maximum(values[0], values[1])
        if node.name == "clamp":
            return np.clip(values[0], values[1], values[2])
        raise ValueError("不支持的公式函数。")

    @staticmethod
    def _physical_source_path(uri: str) -> Path:
        candidate = Path(uri)
        if candidate.is_file():
            return candidate.resolve()
        quoted = [part for part in uri.split('"') if Path(part).is_file()]
        if quoted:
            return Path(quoted[0]).resolve()
        raise ValueError("无法定位栅格源文件。")
