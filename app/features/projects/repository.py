from sqlalchemy.ext.asyncio import AsyncSession

from app.features.projects.schemas import ProjectSummary


class ProjectRepository:
    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session

    async def list_summaries(self) -> list[ProjectSummary]:
        return []
