from __future__ import annotations

from geoalchemy2 import Geometry
from sqlalchemy import JSON, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class MapFeature(TimestampMixin, Base):
    __tablename__ = "map_features"
    __table_args__ = (
        Index("ix_map_features_layer_updated", "layer_id", "updated_at"),
        Index("ix_map_features_source", "layer_id", "source_feature_id"),
        Index("ix_map_features_geom_gist", "geom", postgresql_using="gist"),
        Index("ix_map_features_properties_gin", "properties", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    layer_id: Mapped[int] = mapped_column(ForeignKey("layers.id"), index=True)
    source_feature_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    geom: Mapped[object] = mapped_column(Geometry(geometry_type="GEOMETRY", srid=3857), nullable=False)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    bbox: Mapped[dict] = mapped_column(JSON, default=dict)
    area: Mapped[float | None] = mapped_column(Float, nullable=True)
    perimeter: Mapped[float | None] = mapped_column(Float, nullable=True)
    revision: Mapped[int] = mapped_column(default=1)

    layer: Mapped["Layer"] = relationship(back_populates="features")


class FeaturePropertyIndex(TimestampMixin, Base):
    __tablename__ = "feature_property_indexes"
    __table_args__ = (
        Index("ix_feature_property_layer_field", "layer_id", "field_name"),
        Index("ix_feature_property_value", "field_name", "normalized_value"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    layer_id: Mapped[int] = mapped_column(ForeignKey("layers.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(120))
    normalized_value: Mapped[str] = mapped_column(String(500))
    feature_count: Mapped[int] = mapped_column(default=0)
