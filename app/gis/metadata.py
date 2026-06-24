from dataclasses import dataclass


@dataclass(frozen=True)
class LayerMetadata:
    name: str
    geometry_type: str
    feature_count: int
    crs: str | None
    bounds: tuple[float, float, float, float] | None


SUPPORTED_IMPORT_FORMATS = {
    ".geojson": "GeoJSON",
    ".gpkg": "GeoPackage",
    ".kml": "KML",
    ".zip": "Shapefile ZIP",
}
