"""Prediction and feature models — ML classification outputs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HotspotFeature(Base):
    """Engineered feature vector for a single hotspot."""

    __tablename__ = "hotspot_features"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    hotspot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("hotspots.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Spatial proximity & infrastructure
    dist_nearest_facility: Mapped[float | None] = mapped_column(Float)
    is_inside_facility: Mapped[bool | None] = mapped_column(Boolean, default=False)
    nearby_facility_count_1km: Mapped[int | None] = mapped_column(Integer, default=0)
    nearby_facility_count_5km: Mapped[int | None] = mapped_column(Integer, default=0)
    dist_nearest_road: Mapped[float | None] = mapped_column(Float)
    dist_nearest_forest: Mapped[float | None] = mapped_column(Float)
    dist_nearest_cropland: Mapped[float | None] = mapped_column(Float)
    dist_nearest_mine: Mapped[float | None] = mapped_column(Float)
    dist_nearest_settlement: Mapped[float | None] = mapped_column(Float)

    # Temporal counts & persistence
    nearby_hotspot_count_24h: Mapped[int | None] = mapped_column(Integer, default=0)
    nearby_hotspot_count_7d: Mapped[int | None] = mapped_column(Integer, default=0)
    nearby_hotspot_count_30d: Mapped[int | None] = mapped_column(Integer, default=0)
    nearby_hotspot_count_90d: Mapped[int | None] = mapped_column(Integer, default=0)
    persistence_score: Mapped[float | None] = mapped_column(Float, default=0.0)
    persistence_score_30d: Mapped[float | None] = mapped_column(Float, default=0.0)
    recurrence_rate: Mapped[float | None] = mapped_column(Float, default=0.0)

    # Historical thermal baselines
    historical_median_frp: Mapped[float | None] = mapped_column(Float)
    historical_max_frp: Mapped[float | None] = mapped_column(Float)
    frp_to_historical_ratio: Mapped[float | None] = mapped_column(Float)

    # Cluster & Spatial spread
    cluster_size: Mapped[int | None] = mapped_column(Integer, default=1)
    cluster_spread_km: Mapped[float | None] = mapped_column(Float, default=0.0)
    cluster_direction_deg: Mapped[float | None] = mapped_column(Float, default=0.0)
    spatial_density_5km: Mapped[float | None] = mapped_column(Float, default=0.0)

    # Environmental & Satellite indices
    land_cover_class: Mapped[int | None] = mapped_column(Integer)
    ndvi_value: Mapped[float | None] = mapped_column(Float)
    nbr_value: Mapped[float | None] = mapped_column(Float)
    ndmi_value: Mapped[float | None] = mapped_column(Float)
    delta_nbr: Mapped[float | None] = mapped_column(Float)
    lst_delta: Mapped[float | None] = mapped_column(Float)
    cloud_cover_fraction: Mapped[float | None] = mapped_column(Float)
    imagery_available: Mapped[bool | None] = mapped_column(Boolean, default=True)

    # Contextual
    is_nighttime: Mapped[bool | None] = mapped_column(Boolean)
    day_of_year: Mapped[int | None] = mapped_column(Integer)

    extra_features: Mapped[dict | None] = mapped_column(JSON)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    hotspot = relationship("Hotspot", back_populates="features")

    __table_args__ = (
        Index("idx_hotspot_features_hotspot_id", "hotspot_id"),
    )


class Prediction(Base):
    """ML classification result for a hotspot."""

    __tablename__ = "predictions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    hotspot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("hotspots.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("model_versions.id", ondelete="SET NULL"),
        nullable=True,
    )

    predicted_class: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    stage1_class: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stage1_probabilities: Mapped[dict | None] = mapped_column(JSON)
    stage2_class: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stage2_probabilities: Mapped[dict | None] = mapped_column(JSON)
    class_probabilities: Mapped[dict | None] = mapped_column(JSON)
    feature_importances: Mapped[dict | None] = mapped_column(JSON)
    explanation: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    predicted_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    hotspot = relationship("Hotspot", back_populates="predictions")
    model_version = relationship("ModelVersion", back_populates="predictions")
    feedback_entries = relationship(
        "AnalystFeedback", back_populates="prediction", lazy="selectin"
    )

    __table_args__ = (
        Index("idx_predictions_hotspot_id", "hotspot_id"),
        Index("idx_predictions_predicted_class", "predicted_class"),
    )
