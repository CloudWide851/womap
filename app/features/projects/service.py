from app.features.projects.repository import ProjectRepository
from app.features.projects.schemas import ProjectSummary


class ProjectService:
    def __init__(self, repository: ProjectRepository | None = None) -> None:
        self.repository = repository or ProjectRepository()

    async def list_projects(self) -> list[ProjectSummary]:
        return await self.repository.list_summaries()
