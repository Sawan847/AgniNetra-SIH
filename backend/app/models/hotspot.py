"""Hotspot model — thermal anomaly detections from NASA FIRMS."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone

from geoalchemy2 import Geometry
from sqlalchemy import Date, DateTime, Float, Index, String, Time, Uuid
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Hotspot(Base):
    """A single thermal anomaly detection from satellite sensors."""

    __tablename__ = "hotspots"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[str | None] = mapped_column(
        String(100), unique=True, index=True, doc="Deterministic event hash/id"
    )
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    geom: Mapped[str] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=False,
    )

    # Thermal properties
    brightness: Mapped[float | None] = mapped_column(Float)
    bright_ti4: Mapped[float | None] = mapped_column(Float)
    bright_ti5: Mapped[float | None] = mapped_column(Float)
    frp: Mapped[float | None] = mapped_column(Float, doc="Fire Radiative Power (MW)")
    confidence: Mapped[float | None] = mapped_column(Float)

    # Sensor metadata
    satellite: Mapped[str | None] = mapped_column(String(50))
    instrument: Mapped[str | None] = mapped_column(String(50))
    acq_date: Mapped[date | None] = mapped_column(Date)
    acq_time: Mapped[time | None] = mapped_column(Time)
    daynight: Mapped[str | None] = mapped_column(String(1))
    source: Mapped[str | None] = mapped_column(String(50))

    # Raw metadata preserved from source
    raw_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Tracking
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )

    # Relationships
    features = relationship("HotspotFeature", back_populates="hotspot", lazy="selectin", cascade="all, delete-orphan")
    predictions = relationship("Prediction", back_populates="hotspot", lazy="selectin", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="hotspot", lazy="selectin", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_hotspots_geom", "geom", postgresql_using="gist"),
        Index("idx_hotspots_acq_date", "acq_date"),
        Index("idx_hotspots_ingestion_run_id", "ingestion_run_id"),
    )
