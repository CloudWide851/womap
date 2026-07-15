from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.projects.repository import DEFAULT_PROJECT_NAME, ProjectRepository
from app.models.layer import Layer
from app.models.project import Project


class WorkspaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ensure_default(self) -> Project:
        project = await ProjectRepository(self.session).ensure_default_project()
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def list_projects(self) -> list[Project]:
        return list(
            (
                await self.session.scalars(
                    select(Project).order_by(Project.created_at, Project.id)
                )
            ).all()
        )

    async def get_project(self, workspace_id: int) -> Project | None:
        project = await self.session.get(Project, workspace_id)
        if project is not None:
            await self.session.refresh(project)
        return project

    async def name_exists(self, name: str, exclude_id: int | None = None) -> bool:
        statement = select(Project.id).where(func.lower(Project.name) == name.lower())
        if exclude_id is not None:
            statement = statement.where(Project.id != exclude_id)
        return (await self.session.scalar(statement)) is not None

    async def list_layers(self) -> list[Layer]:
        layers = (
            await self.session.scalars(
                select(Layer).where(Layer.visible.is_(True)).order_by(Layer.created_at, Layer.id)
            )
        ).all()
        return [layer for layer in layers if not (layer.performance or {}).get("staging")]

    async def create_project(
        self,
        *,
        name: str,
        default_basemap: str,
        current_view: dict,
    ) -> Project:
        project = Project(
            name=name,
            default_basemap=default_basemap,
            current_view=current_view,
            workspace_path=None,
        )
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def save_project(self, project: Project) -> Project:
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def delete_project(self, project: Project) -> None:
        if project.name == DEFAULT_PROJECT_NAME:
            raise ValueError("默认工作空间不能删除。")
        await self.session.delete(project)
        await self.session.commit()
