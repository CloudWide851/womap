from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from rasterio.shutil import copy as rio_copy
from rasterio.transform import from_origin

from app.features.imports.scanner import DatasetScanner
from app.features.rasters.processor import RasterProcessor
from app.features.rasters.router import get_raster_service, router
from app.features.rasters.schemas import FormulaNode
from app.features.rasters.service import RasterService
from app.features.rasters.storage import RasterStorage


def _write_tiff(path: Path, *, driver: str = "GTiff", bigtiff: bool = False) -> Path:
    data = np.arange(3 * 16 * 16, dtype="uint16").reshape(3, 16, 16)
    with rasterio.open(
        path,
        "w",
        driver=driver,
        width=16,
        height=16,
        count=3,
        dtype="uint16",
        crs="EPSG:4326",
        transform=from_origin(113.0, 24.0, 0.001, 0.001),
        nodata=65535,
        BIGTIFF="YES" if bigtiff else "IF_NEEDED",
    ) as dataset:
        dataset.write(data)
    return path


def test_scanner_discovers_raster_formats_and_sanitizes_catalog(tmp_path: Path) -> None:
    source = _write_tiff(tmp_path / "scene.tif", bigtiff=True)
    _write_tiff(tmp_path / "terrain.img", driver="HFA")
    rio_copy(source, tmp_path / "ortho.jp2", driver="JP2OpenJPEG")
    (tmp_path / "mosaic.vrt").write_text(
        """<VRTDataset rasterXSize="16" rasterYSize="16">
  <SRS>EPSG:4326</SRS>
  <GeoTransform>113,0.001,0,24,0,-0.001</GeoTransform>
  <VRTRasterBand dataType="UInt16" band="1">
    <SimpleSource><SourceFilename relativeToVRT="1">scene.tif</SourceFilename>
    <SourceBand>1</SourceBand><SourceProperties RasterXSize="16" RasterYSize="16" DataType="UInt16" BlockXSize="16" BlockYSize="16"/>
    <SrcRect xOff="0" yOff="0" xSize="16" ySize="16"/><DstRect xOff="0" yOff="0" xSize="16" ySize="16"/></SimpleSource>
  </VRTRasterBand>
</VRTDataset>""",
        encoding="utf-8",
    )
    (tmp_path / "legacy.hdf").write_bytes(b"not-an-hdf4-file")
    (tmp_path / "cube.nc").write_bytes(b"not-a-netcdf-file")

    catalog = DatasetScanner().scan("source-a", tmp_path)
    by_name = {dataset.relative_path: dataset for dataset in catalog.datasets}

    assert by_name["scene.tif"].dataset_kind == "raster"
    assert by_name["scene.tif"].raster is not None
    assert by_name["scene.tif"].raster.band_count == 3
    assert by_name["terrain.img"].format == "img"
    assert by_name["ortho.jp2"].format == "jp2"
    assert by_name["mosaic.vrt"].valid is True
    assert by_name["legacy.hdf"].valid is False
    assert by_name["cube.nc"].valid is False
    serialized = catalog.model_dump_json()
    assert str(tmp_path) not in serialized
    assert "source_uri" not in serialized


@pytest.mark.parametrize(
    "source_filename,relative",
    [
        ("../outside.tif", "1"),
        ("C:\\outside.tif", "1"),
        ("https://example.com/a.tif", "1"),
        ("/vsicurl/https://example.com/a.tif", "1"),
        ("scene.tif", "0"),
    ],
)
def test_vrt_rejects_external_or_non_relative_sources(
    tmp_path: Path, source_filename: str, relative: str
) -> None:
    (tmp_path / "bad.vrt").write_text(
        f"<VRTDataset><VRTRasterBand><SimpleSource><SourceFilename relativeToVRT=\"{relative}\">"
        f"{source_filename}</SourceFilename></SimpleSource></VRTRasterBand></VRTDataset>",
        encoding="utf-8",
    )

    dataset = DatasetScanner().scan("source-a", tmp_path).datasets[0]

    assert dataset.valid is False
    assert "相对本地引用" in dataset.errors[0] or "根目录" in dataset.errors[0]


def test_processor_creates_managed_epsg3857_cog(tmp_path: Path) -> None:
    source = _write_tiff(tmp_path / "source.tiff")
    storage = RasterStorage(str(tmp_path / "store"), str(tmp_path / "scratch"), 1)

    result = RasterProcessor(storage).to_cog(
        str(source),
        dataset_id="dataset123",
        fingerprint="a" * 64,
        source_crs="EPSG:4326",
    )

    assert result.path.is_file()
    assert storage.root in result.path.parents
    assert result.metadata["band_count"] == 3
    assert result.metadata["block_shapes"][0] == [512, 512]
    assert result.bounds["max_x"] > result.bounds["min_x"]
    assert result.phase_timings.total_ms >= result.phase_timings.preflight_ms
    assert result.phase_timings.combined_phases == (
        "read_warp",
        "write_compress",
        "overview",
    )
    assert result.space_estimate.scratch_required_bytes > result.space_estimate.source_bytes
    with rasterio.open(result.path) as dataset:
        assert dataset.crs.to_epsg() == 3857
        assert dataset.tags(ns="IMAGE_STRUCTURE").get("LAYOUT") == "COG"


def test_formula_validation_and_numpy_evaluation_are_bounded() -> None:
    formula = FormulaNode(
        kind="binary",
        operator="/",
        left=FormulaNode(kind="binary", operator="-", left=FormulaNode(kind="band", band=2), right=FormulaNode(kind="band", band=1)),
        right=FormulaNode(kind="binary", operator="+", left=FormulaNode(kind="band", band=2), right=FormulaNode(kind="band", band=1)),
    )
    RasterProcessor.validate_formula(formula, band_count=3)
    result = RasterProcessor.evaluate_formula(
        formula,
        {1: np.array([1.0, 2.0]), 2: np.array([3.0, 6.0])},
    )
    np.testing.assert_allclose(result, np.array([0.5, 0.5]))

    with pytest.raises(ValueError, match="波段编号"):
        RasterProcessor.validate_formula(FormulaNode(kind="band", band=4), band_count=3)
    with pytest.raises(ValueError, match="公式常量"):
        RasterProcessor.validate_formula(FormulaNode(kind="number", value=float("inf")))


def test_histogram_and_pixel_queries_use_small_reads(tmp_path: Path) -> None:
    source = _write_tiff(tmp_path / "source.tif")
    histogram = RasterService._histogram(source, 7, 1, 16)
    pixel = RasterService._pixel(source, 7, 113.0005, 23.9995, "EPSG:4326")

    assert histogram.layer_id == 7
    assert len(histogram.bins) == 16
    assert histogram.sample_count == 256
    assert pixel.layer_id == 7
    assert len(pixel.values) == 3


def test_cleanup_only_deletes_orphans_and_scratch(tmp_path: Path) -> None:
    storage = RasterStorage(str(tmp_path / "store"), str(tmp_path / "scratch"), 1)
    referenced = storage.root / "referenced.tif"
    orphan = storage.root / "orphan.tif"
    temporary = storage.scratch / "failed.part"
    referenced.write_bytes(b"keep")
    orphan.write_bytes(b"remove")
    temporary.write_bytes(b"temp")

    deleted, freed = storage.cleanup_orphans({referenced.resolve()})

    assert referenced.exists()
    assert not orphan.exists()
    assert not temporary.exists()
    assert deleted == 2
    assert freed == len(b"remove") + len(b"temp")


class _AssetService:
    def __init__(self, path: Path) -> None:
        self.path = path

    async def asset(self, layer_id: int):
        assert layer_id == 9
        return self.path, '"fixture-etag"', "Tue, 15 Jul 2026 00:00:00 GMT"


def test_asset_endpoint_supports_range_suffix_etag_and_416(tmp_path: Path) -> None:
    asset = tmp_path / "asset.tif"
    asset.write_bytes(b"0123456789")
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/rasters")

    async def override_service():
        yield _AssetService(asset)

    app.dependency_overrides[get_raster_service] = override_service
    client = TestClient(app)

    full = client.get("/api/v1/rasters/9/asset")
    prefix = client.get("/api/v1/rasters/9/asset", headers={"Range": "bytes=2-5"})
    suffix = client.get("/api/v1/rasters/9/asset", headers={"Range": "bytes=-3"})
    cached = client.get(
        "/api/v1/rasters/9/asset", headers={"If-None-Match": '"fixture-etag"'}
    )
    invalid = client.get("/api/v1/rasters/9/asset", headers={"Range": "bytes=20-30"})

    assert full.status_code == 200
    assert full.content == b"0123456789"
    assert full.headers["content-length"] == "10"
    assert full.headers["accept-ranges"] == "bytes"
    assert full.headers["etag"] == '"fixture-etag"'
    assert full.headers["last-modified"] == "Tue, 15 Jul 2026 00:00:00 GMT"
    assert "content-encoding" not in full.headers
    assert prefix.status_code == 206
    assert prefix.content == full.content[2:6]
    assert prefix.headers["content-range"] == "bytes 2-5/10"
    assert "content-encoding" not in prefix.headers
    assert suffix.content == full.content[-3:]
    assert "content-encoding" not in suffix.headers
    assert cached.status_code == 304
    assert cached.content == b""
    assert invalid.status_code == 416
    assert invalid.headers["content-range"] == "bytes */10"
