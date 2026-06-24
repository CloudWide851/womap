from sqlalchemy import JSON, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class BasemapProvider(TimestampMixin, Base):
    __tablename__ = "basemap_providers"
    __table_args__ = (Index("ix_basemap_providers_enabled", "enabled"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    provider_type: Mapped[str] = mapped_column(String(20), default="xyz")
    name: Mapped[str] = mapped_column(String(120))
    url_template: Mapped[str] = mapped_column(String(1000))
    api_key: Mapped[str] = mapped_column(String(300), default="")
    subdomains: Mapped[list] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(default=True)
