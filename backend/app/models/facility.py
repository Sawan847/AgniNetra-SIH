"""Industrial facility model — from OpenStreetMap or manual entry."""

from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Index, String, Uuid
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IndustrialFacility(Base):
    """A known industrial infrastructure point or polygon."""

    __tablename__ = "industrial_facilities"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str | None] = mapped_column(String(255))
    facility_type: Mapped[str | None] = mapped_column(
        String(100), doc="refinery, power_plant, factory, etc."
    )
    osm_id: Mapped[str | None] = mapped_column(String(50), unique=True)

    # Geometry
    location: Mapped[str] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=False
    )
    footprint: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326), nullable=True
    )

    source: Mapped[str | None] = mapped_column(String(50), default="OSM")
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("idx_facilities_location", "location", postgresql_using="gist"),
        Index("idx_facilities_footprint", "footprint", postgresql_using="gist"),
    )
