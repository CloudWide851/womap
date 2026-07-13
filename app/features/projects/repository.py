from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.projects.schemas import ProjectSummary
from app.models.project import Project

DEFAULT_PROJECT_NAME = "本地工作台"


class ProjectRepository:
    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session

    async def list_summaries(self) -> list[ProjectSummary]:
        return []

    async def ensure_default_project(self) -> Project:
        if self.session is None:
            raise RuntimeError("数据库会话不可用。")
        project = await self.session.scalar(
            select(Project).where(Project.name == DEFAULT_PROJECT_NAME)
        )
        if project is None:
            project = Project(
                name=DEFAULT_PROJECT_NAME,
                default_basemap="amap-vector",
                current_view={},
            )
            self.session.add(project)
            await self.session.flush()
        return project
