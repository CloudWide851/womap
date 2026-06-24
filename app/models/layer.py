from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Layer(TimestampMixin, Base):
    __tablename__ = "layers"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    source_type: Mapped[str] = mapped_column(String(60))
    geometry_type: Mapped[str] = mapped_column(String(40))
    feature_count: Mapped[int] = mapped_column(default=0)
    crs: Mapped[str | None] = mapped_column(String(120), nullable=True)
    bounds: Mapped[dict] = mapped_column(JSON, default=dict)
    style: Mapped[dict] = mapped_column(JSON, default=dict)
    data_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    visible: Mapped[bool] = mapped_column(default=True)
    locked: Mapped[bool] = mapped_column(default=False)
    opacity: Mapped[float] = mapped_column(default=1.0)

    project: Mapped["Project"] = relationship(back_populates="layers")
