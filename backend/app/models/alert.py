"""Alert model — notifications triggered by hotspot classifications."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Alert(Base):
    """An alert raised for a classified hotspot."""

    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    hotspot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("hotspots.id", ondelete="CASCADE"),
        nullable=False,
    )
    prediction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("predictions.id", ondelete="SET NULL"),
        nullable=True,
    )

    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, doc="critical, high, medium, low"
    )
    alert_type: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        doc="active, acknowledged, resolved, false_positive",
    )
    description: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    hotspot = relationship("Hotspot", back_populates="alerts")

    __table_args__ = (
        Index("idx_alerts_status_severity", "status", "severity"),
    )
