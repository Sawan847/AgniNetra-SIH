"""Land cover model — ESA WorldCover or Copernicus land classification polygons."""

from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LandCover(Base):
    """A land-cover classification polygon."""

    __tablename__ = "land_cover"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    cover_class: Mapped[int] = mapped_column(
        Integer, nullable=False, doc="ESA WorldCover numeric class code"
    )
    cover_label: Mapped[str] = mapped_column(String(100), nullable=False)
    geom: Mapped[str] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326), nullable=False
    )
    year: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str | None] = mapped_column(String(50), default="ESA")

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("idx_land_cover_geom", "geom", postgresql_using="gist"),
    )
