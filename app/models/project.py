from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    workspace_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    default_basemap: Mapped[str] = mapped_column(String(80), default="osm")
    current_view: Mapped[dict] = mapped_column(JSON, default=dict)

    layers: Mapped[list["Layer"]] = relationship(back_populates="project")
