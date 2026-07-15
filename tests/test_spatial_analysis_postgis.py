from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from geoalchemy2.shape import from_shape
from shapely.geometry import LineString, Point, Polygon
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.features.map_features.repository import MapFeatureRepository
from app.features.map_features.service import MapFeatureService
from app.features.spatial_analyses.repository import SpatialAnalysisRepository
from app.features.spatial_analyses.schemas import SpatialAnalysisCreate
from app.features.spatial_analyses.service import SpatialAnalysisService
from app.features.workspaces.repository import WorkspaceRepository
from app.features.workspaces.schemas import (
    WorkspaceDefinition,
    WorkspaceFeatureSelection,
    WorkspaceLayerConfig,
)
from app.features.workspaces.service import WorkspaceService
from app.models.layer import Layer
from app.models.map_feature import MapFeature
from app.models.project import Project
from app.shared.config import get_settings


@pytest_asyncio.fixture
async def postgis_session() -> AsyncGenerator[AsyncSession, None]:
    url = get_settings().database.sqlalchemy_url().set(host="127.0.0.1")
    admin_engine = create_async_engine(
        url,
        pool_pre_ping=True,
        connect_args={"ssl": False},
    )
    schema = f"womap_test_{uuid4().hex}"
    async with admin_engine.begin() as connection:
        await connection.execute(text("SELECT postgis_version()"))
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url,
        connect_args={
            "server_settings": {"search_path": f"{schema},public"},
            "ssl": False,
        },
        pool_pre_ping=True,
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection,
                    checkfirst=False,
                )
            )
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            yield session
    finally:
        await engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin_engine.dispose()


def feature(layer_id: int, geometry, feature_id: int, name: str) -> MapFeature:
    min_x, min_y, max_x, max_y = geometry.bounds
    return MapFeature(
        id=feature_id,
        layer_id=layer_id,
        source_feature_id=f"source-{feature_id}",
        geom=from_shape(geometry, srid=3857),
        properties={"名称": name},
        bbox={"min_x": min_x, "min_y": min_y, "max_x": max_x, "max_y": max_y},
        area=float(geometry.area) if isinstance(geometry, Polygon) else None,
        perimeter=float(geometry.length) if isinstance(geometry, Polygon) else None,
        revision=1,
    )


@pytest.mark.asyncio
async def test_postgis_feature_update_and_delete_recompute_layer_aggregate(
    postgis_session: AsyncSession,
) -> None:
    session = postgis_session
    project = Project(
        id=80,
        name="编辑聚合测试",
        default_basemap="amap-vector",
        current_view={},
    )
    layer = Layer(
        id=80,
        project_id=project.id,
        name="手工图斑",
        source_type="manual",
        geometry_type="Polygon",
        feature_count=2,
        crs="EPSG:3857",
        bounds={"min_x": 0, "min_y": 0, "max_x": 30, "max_y": 30},
        style={},
        fields=[],
        performance={},
        visible=True,
        locked=False,
        opacity=1,
    )
    first = feature(
        layer.id,
        Polygon([(0, 0), (10, 0), (10, 10), (0, 0)]),
        801,
        "待移动",
    )
    second = feature(
        layer.id,
        Polygon([(20, 20), (30, 20), (30, 30), (20, 20)]),
        802,
        "保留边界",
    )
    session.add(project)
    session.add(layer)
    session.add_all([first, second])
    await session.commit()
    repository = MapFeatureRepository(session)
    moved = Polygon([(100, 100), (110, 100), (110, 110), (100, 100)])

    item, summary = await repository.update_polygon_feature(
        layer,
        first,
        moved,
        {"名称": "已移动"},
    )

    assert item.revision == 2
    assert summary.feature_count == 2
    assert summary.bounds == {
        "min_x": 20.0,
        "min_y": 20.0,
        "max_x": 110.0,
        "max_y": 110.0,
    }

    after_first_delete = await repository.delete_polygon_feature(layer, second)
    assert after_first_delete.feature_count == 1
    assert after_first_delete.bounds == {
        "min_x": 100.0,
        "min_y": 100.0,
        "max_x": 110.0,
        "max_y": 110.0,
    }

    empty = await repository.delete_polygon_feature(layer, first)
    assert empty.feature_count == 0
    assert empty.bounds == {}


@pytest.mark.asyncio
async def test_postgis_analysis_covers_point_line_polygon_workspace_filter_and_stale(
    postgis_session: AsyncSession,
) -> None:
    session = postgis_session
    project = Project(
        id=1,
        name="分析工作空间",
        default_basemap="amap-vector",
        current_view={},
    )
    layers = [
        Layer(
            id=1,
            project_id=1,
            name="面图层",
            source_type="gdb",
            geometry_type="Polygon",
            feature_count=2,
            crs="EPSG:3857",
            bounds={},
            style={},
            fields=[],
            performance={"dataset_id": "polygon", "container": "analysis.gdb", "fingerprint": "p1"},
            visible=True,
            locked=False,
            opacity=1,
        ),
        Layer(
            id=2,
            project_id=1,
            name="线图层",
            source_type="gdb",
            geometry_type="LineString",
            feature_count=1,
            crs="EPSG:3857",
            bounds={},
            style={},
            fields=[],
            performance={"dataset_id": "line", "container": "analysis.gdb", "fingerprint": "l1"},
            visible=True,
            locked=False,
            opacity=1,
        ),
        Layer(
            id=3,
            project_id=1,
            name="点图层",
            source_type="shp",
            geometry_type="Point",
            feature_count=2,
            crs="EPSG:3857",
            bounds={},
            style={},
            fields=[],
            performance={"dataset_id": "point", "container": "points.shp", "fingerprint": "pt1"},
            visible=True,
            locked=False,
            opacity=1,
        ),
        Layer(
            id=4,
            project_id=1,
            name="无命中图层",
            source_type="manual",
            geometry_type="Point",
            feature_count=1,
            crs="EPSG:3857",
            bounds={},
            style={},
            fields=[],
            performance={"fingerprint": "far1"},
            visible=True,
            locked=False,
            opacity=1,
        ),
    ]
    session.add(project)
    session.add_all(layers)
    session.add_all(
        [
            feature(1, Polygon([(0, 0), (100, 0), (100, 100), (0, 0)]), 1, "目标"),
            feature(1, Polygon([(150, 0), (220, 0), (220, 70), (150, 0)]), 2, "邻近面"),
            feature(2, LineString([(-50, 50), (180, 50)]), 3, "穿越线"),
            feature(3, Point(120, 50), 4, "邻近点"),
            feature(3, Point(900, 900), 5, "远点"),
            feature(4, Point(5000, 5000), 6, "无命中点"),
        ]
    )
    project.current_view = WorkspaceDefinition(
        workspace_uuid="33333333-3333-3333-3333-333333333333",
        layers=[
            WorkspaceLayerConfig(layer_id=layer.id, dataset_id=(layer.performance or {}).get("dataset_id"))
            for layer in layers
        ],
    ).model_dump(mode="json")
    await session.commit()

    workspace_service = WorkspaceService(WorkspaceRepository(session))
    service = SpatialAnalysisService(
        SpatialAnalysisRepository(session),
        workspace_service,
        MapFeatureService(MapFeatureRepository(session), workspace_service),
    )
    queued = await service.queue(
        SpatialAnalysisCreate(
            workspace_id=1,
            target_layer_id=1,
            target_feature_id=1,
            distance=300,
            unit="m",
        )
    )
    await service.run(queued.id)
    result = await service.get_result(queued.id)
    summaries = {
        layer.layer_id: layer
        for group in result.groups
        for layer in group.layers
    }
    assert result.job.status == "done"
    assert summaries[1].hit_count == 1  # The target feature itself is excluded.
    assert summaries[1].buffer_area_sqm > 0
    assert summaries[2].direct_intersection_count == 1
    assert summaries[2].buffer_length_m > 0
    assert summaries[3].point_hit_count == 1
    assert summaries[4].exists is False

    page = await service.hits(queued.id, limit=2, cursor=None)
    assert len(page.items) == 2
    assert all(hit.feature_id != 1 for hit in page.items)
    assert page.has_more is True
    second_page = await service.hits(queued.id, limit=10, cursor=page.next_cursor)
    assert {hit.feature_id for hit in page.items + second_page.items} >= {2, 3, 4}

    layers[2].performance = {**layers[2].performance, "fingerprint": "pt2"}
    await session.commit()
    stale = await service.get_result(queued.id)
    assert stale.stale is True
    assert "点图层" in stale.warnings[0]

    project.current_view = WorkspaceDefinition(
        workspace_uuid="33333333-3333-3333-3333-333333333333",
        revision=2,
        layers=[
            WorkspaceLayerConfig(layer_id=1, dataset_id="polygon"),
            WorkspaceLayerConfig(layer_id=2, dataset_id="line"),
            WorkspaceLayerConfig(
                layer_id=3,
                dataset_id="point",
                selection=WorkspaceFeatureSelection(mode="include", feature_ids=[5]),
            ),
            WorkspaceLayerConfig(layer_id=4),
        ],
    ).model_dump(mode="json")
    await session.commit()
    filtered_job = await service.queue(
        SpatialAnalysisCreate(
            workspace_id=1,
            target_layer_id=1,
            target_feature_id=1,
            distance=300,
            unit="m",
        )
    )
    await service.run(filtered_job.id)
    filtered = await service.get_result(filtered_job.id)
    filtered_points = next(
        layer
        for group in filtered.groups
        for layer in group.layers
        if layer.layer_id == 3
    )
    assert filtered_points.hit_count == 0
