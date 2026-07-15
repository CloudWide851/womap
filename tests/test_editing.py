from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon

from app.features.layers.repository import LayerRepository
from app.features.layers.router import get_layer_service
from app.features.layers.schemas import LayerCreate, LayerSummary
from app.features.map_features.repository import MapFeatureRepository
from app.features.map_features.router import get_map_feature_service
from app.features.map_features.schemas import (
    FeatureGeometry,
    MapFeatureCreate,
    MapFeatureItem,
    MapFeatureUpdate,
    PolygonGeometry,
)
from app.features.map_features.service import MapFeatureService
from app.features.projects.repository import ProjectRepository
from app.main import create_app
from conftest import allow_test_auth
from app.models.layer import Layer
from app.models.map_feature import MapFeature
from app.models.project import Project


def polygon_payload(
    coordinates: list[list[float]] | None = None,
) -> MapFeatureCreate:
    return MapFeatureCreate(
        geometry=PolygonGeometry(
            type="Polygon",
            coordinates=[
                coordinates
                or [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 0.0]]
            ],
        ),
        properties={"name": "new parcel"},
    )


def make_layer(**overrides) -> Layer:
    values = {
        "id": 7,
        "project_id": 1,
        "name": "parcels",
        "source_type": "manual",
        "geometry_type": "Polygon",
        "feature_count": 0,
        "crs": "EPSG:3857",
        "bounds": {},
        "style": {},
        "fields": [],
        "performance": {},
        "visible": True,
        "locked": False,
        "opacity": 1.0,
    }
    values.update(overrides)
    return Layer(**values)


class ScalarValues:
    def __init__(self, values: list[str]) -> None:
        self.values = values

    def all(self) -> list[str]:
        return self.values


class ManualLayerSession:
    def __init__(self) -> None:
        self.project = Project(id=1, name="本地工作台")
        self.added: list[object] = []
        self.commits = 0

    async def scalar(self, statement):
        _ = statement
        return self.project

    async def scalars(self, statement) -> ScalarValues:
        _ = statement
        return ScalarValues(["新建图斑图层 1", "新建图斑图层 2", "其他图层"])

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.commits += 1
        self.added[-1].id = 12

    async def refresh(self, value: object) -> None:
        _ = value

    async def rollback(self) -> None:
        raise AssertionError("successful create must not roll back")


@pytest.mark.asyncio
async def test_manual_layer_uses_next_automatic_name_and_defaults() -> None:
    session = ManualLayerSession()

    summary = await LayerRepository(session).create_manual_polygon_layer(None)

    assert summary.id == 12
    assert summary.name == "新建图斑图层 3"
    assert summary.geometry_type == "Polygon"
    assert summary.crs == "EPSG:3857"
    assert summary.visible is True
    assert summary.locked is False
    assert summary.source_type == "manual"
    assert session.commits == 1


class DefaultProjectSession:
    def __init__(self) -> None:
        self.project: Project | None = None
        self.add_count = 0

    async def scalar(self, statement):
        _ = statement
        return self.project

    def add(self, project: Project) -> None:
        self.project = project
        self.add_count += 1

    async def flush(self) -> None:
        assert self.project is not None
        self.project.id = 1


@pytest.mark.asyncio
async def test_default_workspace_project_creation_is_idempotent() -> None:
    session = DefaultProjectSession()
    repository = ProjectRepository(session)

    first = await repository.ensure_default_project()
    second = await repository.ensure_default_project()

    assert first is second
    assert first.name == "本地工作台"
    assert session.add_count == 1


class FeatureSession:
    def __init__(self, fail_commit: bool = False) -> None:
        self.fail_commit = fail_commit
        self.added: list[object] = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.commits += 1
        if self.fail_commit:
            raise RuntimeError("commit failed")
        self.added[-1].id = 21

    async def refresh(self, value: object) -> None:
        _ = value

    async def rollback(self) -> None:
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_polygon_insert_updates_count_and_merges_bounds_atomically() -> None:
    session = FeatureSession()
    layer = make_layer(
        feature_count=2,
        bounds={"min_x": -5.0, "min_y": -4.0, "max_x": 5.0, "max_y": 6.0},
    )

    feature, summary = await MapFeatureRepository(session).create_polygon_feature(
        layer,
        Polygon([(0, 0), (10, 0), (10, 10), (0, 0)]),
        {"name": "A"},
    )

    assert feature.id == 21
    assert feature.properties == {"name": "A"}
    assert summary.feature_count == 3
    assert summary.bounds == {"min_x": -5.0, "min_y": -4.0, "max_x": 10.0, "max_y": 10.0}
    assert session.commits == 1
    assert session.rollbacks == 0


@pytest.mark.asyncio
async def test_polygon_insert_rolls_back_feature_count_and_bounds_on_failure() -> None:
    session = FeatureSession(fail_commit=True)
    original_bounds = {"min_x": 1.0, "min_y": 1.0, "max_x": 2.0, "max_y": 2.0}
    layer = make_layer(feature_count=4, bounds=original_bounds)

    with pytest.raises(RuntimeError, match="commit failed"):
        await MapFeatureRepository(session).create_polygon_feature(
            layer,
            Polygon([(0, 0), (10, 0), (10, 10), (0, 0)]),
            {},
        )

    assert session.rollbacks == 1
    assert layer.feature_count == 4
    assert layer.bounds == original_bounds


class MemoryFeatureRepository(MapFeatureRepository):
    def __init__(self, layer: Layer | None) -> None:
        self.layer = layer
        self.created = 0
        self.feature = (
            MapFeature(
                id=31,
                layer_id=layer.id,
                source_feature_id=None,
                properties={"name": "existing parcel"},
                bbox={},
                area=100.0,
                perimeter=40.0,
                revision=1,
            )
            if layer
            else None
        )

    async def get_layer(self, layer_id: int) -> Layer | None:
        _ = layer_id
        return self.layer

    async def create_polygon_feature(self, layer, polygon, properties):
        self.created += 1
        layer.feature_count += 1
        return (
            MapFeatureItem(
                id=31,
                geometry=FeatureGeometry(type="Polygon", coordinates=[]),
                properties=properties,
            ),
            LayerRepository.to_summary(layer),
        )

    async def get_feature(self, layer_id: int, feature_id: int) -> MapFeature | None:
        if self.feature and self.feature.layer_id == layer_id and self.feature.id == feature_id:
            return self.feature
        return None

    async def update_polygon_feature(self, layer, feature, polygon, properties):
        feature.properties = properties
        feature.revision += 1
        return (
            MapFeatureItem(
                id=feature.id,
                layer_id=layer.id,
                geometry=FeatureGeometry(
                    type="Polygon",
                    coordinates=[[list(point) for point in polygon.exterior.coords]],
                ),
                properties=properties,
                revision=feature.revision,
            ),
            LayerRepository.to_summary(layer),
        )

    async def delete_polygon_feature(self, layer, feature):
        _ = feature
        layer.feature_count = max(0, layer.feature_count - 1)
        self.feature = None
        return LayerRepository.to_summary(layer)


@pytest.mark.parametrize(
    ("coordinates", "message"),
    [
        ([[0, 0], [1, 1], [0, 0]], "三个不同顶点"),
        ([[0, 0], [10, 10], [0, 10], [10, 0], [0, 0]], "自相交"),
    ],
)
def test_polygon_validation_rejects_invalid_geometry(coordinates, message) -> None:
    with pytest.raises(ValueError, match=message):
        MapFeatureService._validate_polygon(polygon_payload(coordinates))


def test_polygon_validation_rejects_empty_geometry() -> None:
    payload = MapFeatureCreate(
        geometry=PolygonGeometry(type="Polygon", coordinates=[]),
    )

    with pytest.raises(ValueError, match="坐标不能为空"):
        MapFeatureService._validate_polygon(payload)


def test_polygon_validation_rejects_zero_area_geometry() -> None:
    with pytest.raises(ValueError):
        MapFeatureService._validate_polygon(
            polygon_payload([[0, 0], [1, 1], [2, 2], [0, 0]])
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("layer", "message"),
    [
        (make_layer(locked=True), "已锁定"),
        (make_layer(visible=False), "已隐藏"),
        (make_layer(geometry_type="Point"), "不支持 Polygon"),
    ],
)
async def test_polygon_creation_rejects_incompatible_layer(layer: Layer, message: str) -> None:
    repository = MemoryFeatureRepository(layer)

    with pytest.raises(RuntimeError, match=message):
        await MapFeatureService(repository).create_polygon_feature(7, polygon_payload())

    assert repository.created == 0


@pytest.mark.asyncio
async def test_polygon_update_uses_optimistic_revision() -> None:
    repository = MemoryFeatureRepository(make_layer(feature_count=1))
    service = MapFeatureService(repository)
    payload = MapFeatureUpdate(**polygon_payload().model_dump(), revision=1)

    response = await service.update_polygon_feature(7, 31, payload)

    assert response.feature.revision == 2
    assert response.feature.properties == {"name": "new parcel"}
    with pytest.raises(RuntimeError, match="其他操作更新"):
        await service.update_polygon_feature(7, 31, payload)


@pytest.mark.asyncio
async def test_polygon_delete_updates_layer_summary() -> None:
    repository = MemoryFeatureRepository(make_layer(feature_count=1))

    response = await MapFeatureService(repository).delete_polygon_feature(7, 31, 1)

    assert response.deleted_feature_id == 31
    assert response.layer.feature_count == 0


class FakeLayerService:
    async def create_layer(self, payload: LayerCreate) -> LayerSummary:
        return LayerRepository.to_summary(make_layer(id=44, name=payload.name or "新建图斑图层 1"))

    async def list_layers(self) -> list[LayerSummary]:
        return []


def api_client(layer: Layer | None) -> TestClient:
    app = allow_test_auth(create_app())
    app.dependency_overrides[get_layer_service] = lambda: FakeLayerService()
    app.dependency_overrides[get_map_feature_service] = lambda: MapFeatureService(
        MemoryFeatureRepository(layer)
    )
    return TestClient(app)


def test_manual_layer_api_returns_201() -> None:
    response = api_client(make_layer()).post(
        "/api/v1/layers",
        json={"name": "  手工图斑  ", "geometry_type": "Polygon"},
    )

    assert response.status_code == 201
    assert response.json()["name"] == "手工图斑"


@pytest.mark.parametrize(
    ("layer", "coordinates", "status_code"),
    [
        (None, None, 404),
        (make_layer(locked=True), None, 409),
        (make_layer(visible=False), None, 409),
        (make_layer(geometry_type="Point"), None, 409),
        (make_layer(), [[0, 0], [1, 1], [0, 0]], 400),
        (make_layer(), None, 201),
    ],
)
def test_polygon_feature_api_status_codes(layer, coordinates, status_code) -> None:
    payload = polygon_payload(coordinates).model_dump()

    response = api_client(layer).post("/api/v1/layers/7/features", json=payload)

    assert response.status_code == status_code
    if status_code == 201:
        assert response.json()["layer"]["feature_count"] == 1
        assert response.json()["feature"]["id"] == 31


def test_polygon_feature_update_and_delete_api() -> None:
    client = api_client(make_layer(feature_count=1))
    payload = MapFeatureUpdate(**polygon_payload().model_dump(), revision=1).model_dump()

    updated = client.put("/api/v1/layers/7/features/31", json=payload)
    deleted = client.delete("/api/v1/layers/7/features/31?revision=1")

    assert updated.status_code == 200
    assert updated.json()["feature"]["revision"] == 2
    assert deleted.status_code == 200
    assert deleted.json()["deleted_feature_id"] == 31
