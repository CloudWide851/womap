from __future__ import annotations

from collections import OrderedDict

from app.features.layers.repository import LayerRepository
from app.features.workspaces.repository import WorkspaceRepository
from app.features.workspaces.schemas import (
    WorkspaceCatalogGroup,
    WorkspaceCatalogResponse,
    WorkspaceCreate,
    WorkspaceDefinition,
    WorkspaceDetail,
    WorkspaceFeatureSelection,
    WorkspaceLayerConfig,
    WorkspaceLayerState,
    WorkspaceSelectionFilter,
    WorkspaceSummary,
    WorkspaceUpdate,
)
from app.features.projects.repository import DEFAULT_PROJECT_NAME
from app.models.layer import Layer
from app.models.project import Project


class WorkspaceConflictError(Exception):
    pass


class WorkspaceService:
    def __init__(self, repository: WorkspaceRepository) -> None:
        self.repository = repository

    async def list_workspaces(self) -> list[WorkspaceSummary]:
        await self.repository.ensure_default()
        projects = await self.repository.list_projects()
        layers = await self.repository.list_layers()
        return [self._summary(project, self._definition(project, layers)) for project in projects]

    async def get_workspace(self, workspace_id: int) -> WorkspaceDetail:
        project = await self.repository.get_project(workspace_id)
        if project is None:
            raise KeyError(workspace_id)
        layers = await self.repository.list_layers()
        definition = self._definition(project, layers)
        return self._detail(project, definition, layers)

    async def create_workspace(self, payload: WorkspaceCreate) -> WorkspaceDetail:
        if await self.repository.name_exists(payload.name):
            raise WorkspaceConflictError("工作空间名称已存在。")
        definition = WorkspaceDefinition(
            description=payload.description,
            view=payload.view,
            layers=self._normalized_configs(payload.layers),
        )
        project = await self.repository.create_project(
            name=payload.name,
            default_basemap=payload.default_basemap,
            current_view=definition.model_dump(mode="json"),
        )
        return await self.get_workspace(project.id)

    async def update_workspace(self, workspace_id: int, payload: WorkspaceUpdate) -> WorkspaceDetail:
        project = await self.repository.get_project(workspace_id)
        if project is None:
            raise KeyError(workspace_id)
        layers = await self.repository.list_layers()
        current = self._definition(project, layers)
        if current.revision != payload.revision:
            raise WorkspaceConflictError("工作空间已在其他窗口更新，请刷新后重试。")
        if await self.repository.name_exists(payload.name, exclude_id=workspace_id):
            raise WorkspaceConflictError("工作空间名称已存在。")
        updated = WorkspaceDefinition(
            workspace_uuid=current.workspace_uuid,
            revision=current.revision + 1,
            description=payload.description,
            view=payload.view,
            layers=self._normalized_configs(payload.layers),
        )
        project.name = payload.name
        project.default_basemap = payload.default_basemap
        project.current_view = updated.model_dump(mode="json")
        await self.repository.save_project(project)
        return await self.get_workspace(project.id)

    async def delete_workspace(self, workspace_id: int) -> None:
        project = await self.repository.get_project(workspace_id)
        if project is None:
            raise KeyError(workspace_id)
        await self.repository.delete_project(project)

    async def catalog(self) -> WorkspaceCatalogResponse:
        groups: OrderedDict[str, WorkspaceCatalogGroup] = OrderedDict()
        for layer in await self.repository.list_layers():
            summary = LayerRepository.to_summary(layer)
            provenance = summary.provenance
            if provenance.format == "gdb":
                key = f"gdb:{provenance.source_id}:{provenance.container}"
                label = provenance.container or "FileGDB"
            elif provenance.format == "shp":
                key = f"shp:{provenance.source_id}:{provenance.container}"
                label = provenance.container or "Shapefile"
            elif provenance.format == "workspace":
                key = f"workspace:{provenance.source_id}:{provenance.container}"
                label = provenance.container or "工作空间包"
            else:
                key = "manual"
                label = "本地编辑"
            if key not in groups:
                groups[key] = WorkspaceCatalogGroup(
                    key=key,
                    label=label,
                    format=provenance.format,
                    source_id=provenance.source_id,
                    container=provenance.container,
                )
            groups[key].layers.append(summary)
        return WorkspaceCatalogResponse(groups=list(groups.values()))

    async def selection_filter(
        self,
        workspace_id: int,
        layer_id: int,
    ) -> WorkspaceSelectionFilter:
        detail = await self.get_workspace(workspace_id)
        for state in detail.layers:
            if state.layer.id == layer_id:
                selection = state.config.selection
                return WorkspaceSelectionFilter(
                    layer_id=layer_id,
                    feature_ids=selection.feature_ids,
                    source_feature_ids=selection.source_feature_ids,
                    include_all=selection.mode == "all",
                    visible=state.config.visible,
                )
        raise KeyError(layer_id)

    @staticmethod
    def _normalized_configs(configs: list[WorkspaceLayerConfig]) -> list[WorkspaceLayerConfig]:
        seen: set[tuple[int, str | None]] = set()
        normalized: list[WorkspaceLayerConfig] = []
        for index, config in enumerate(configs):
            key = (config.layer_id, config.dataset_id)
            if key in seen:
                continue
            seen.add(key)
            selection = config.selection
            if selection.mode == "all":
                selection = WorkspaceFeatureSelection(mode="all")
            normalized.append(config.model_copy(update={"order": index, "selection": selection}))
        return normalized

    @staticmethod
    def _definition(project: Project, layers: list[Layer]) -> WorkspaceDefinition:
        raw = dict(project.current_view or {})
        if raw.get("schema_version") == "womap.workspace/v1":
            return WorkspaceDefinition.model_validate(raw)
        if project.name == DEFAULT_PROJECT_NAME:
            configs = [
                WorkspaceLayerConfig(
                    layer_id=layer.id,
                    dataset_id=(layer.performance or {}).get("dataset_id"),
                    visible=True,
                    opacity=layer.opacity,
                    order=index,
                    raster_style=(
                        (layer.style or {}).get("raster")
                        if layer.geometry_type == "Raster"
                        else None
                    ),
                )
                for index, layer in enumerate(layers)
            ]
            return WorkspaceDefinition(description="默认包含当前全部后端图层。", layers=configs)
        return WorkspaceDefinition(description="旧工作空间尚未配置数据。")

    @staticmethod
    def _summary(project: Project, definition: WorkspaceDefinition) -> WorkspaceSummary:
        return WorkspaceSummary(
            id=project.id,
            name=project.name,
            description=definition.description,
            default_basemap=project.default_basemap,
            revision=definition.revision,
            layer_count=len(definition.layers),
            is_default=project.name == DEFAULT_PROJECT_NAME,
            updated_at=project.updated_at,
        )

    @classmethod
    def _detail(
        cls,
        project: Project,
        definition: WorkspaceDefinition,
        layers: list[Layer],
    ) -> WorkspaceDetail:
        by_id = {layer.id: layer for layer in layers}
        by_dataset = {
            str((layer.performance or {}).get("dataset_id")): layer
            for layer in layers
            if (layer.performance or {}).get("dataset_id")
        }
        states: list[WorkspaceLayerState] = []
        warnings: list[str] = []
        for config in sorted(definition.layers, key=lambda item: item.order):
            layer = by_dataset.get(config.dataset_id) if config.dataset_id else by_id.get(config.layer_id)
            if layer is None:
                warnings.append(
                    f"图层引用已失效：{config.dataset_id or config.layer_id}，请重新选择数据。"
                )
                continue
            resolved = config.model_copy(update={"layer_id": layer.id})
            summary = LayerRepository.to_summary(layer)
            style = dict(summary.style)
            if summary.kind == "raster" and config.raster_style is not None:
                style["raster"] = config.raster_style.model_dump(mode="json")
            summary = summary.model_copy(
                update={"visible": config.visible, "opacity": config.opacity, "style": style}
            )
            states.append(WorkspaceLayerState(config=resolved, layer=summary))
        summary = cls._summary(project, definition)
        return WorkspaceDetail(
            **summary.model_dump(),
            schema_version=definition.schema_version,
            workspace_uuid=definition.workspace_uuid,
            view=definition.view,
            layers=states,
            warnings=warnings,
        )
