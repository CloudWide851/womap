from __future__ import annotations

import importlib.util
import os
from pathlib import Path


def configure_bundled_gdal() -> None:
    """Keep Rasterio's GDAL/PROJ runtime paired with its bundled data files."""
    spec = importlib.util.find_spec("rasterio")
    if spec is None or not spec.submodule_search_locations:
        return
    package_root = Path(next(iter(spec.submodule_search_locations)))
    proj_data = package_root / "proj_data"
    gdal_data = package_root / "gdal_data"
    if (proj_data / "proj.db").is_file():
        # PROJ_LIB is still honored by GDAL builds on Windows and can otherwise
        # leak in from a separately installed PostGIS/PROJ distribution.
        os.environ["PROJ_LIB"] = str(proj_data)
        os.environ["PROJ_DATA"] = str(proj_data)
    if gdal_data.is_dir():
        os.environ["GDAL_DATA"] = str(gdal_data)
