"""Analyst feedback model — human-in-the-loop corrections."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AnalystFeedback(Base):
    """Human correction or confirmation of an ML prediction / hotspot."""

    __tablename__ = "analyst_feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    prediction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("predictions.id", ondelete="CASCADE"),
        nullable=True,
    )
    hotspot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("hotspots.id", ondelete="CASCADE"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    suggested_class: Mapped[str | None] = mapped_column(String(100), nullable=True)
    verified_class: Mapped[str | None] = mapped_column(String(100), nullable=True)
    corrected_class: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    reviewer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    label_source: Mapped[str] = mapped_column(
        String(50), default="analyst_verified", doc="analyst_verified, weak_rule, model_inference"
    )
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    prediction = relationship("Prediction", back_populates="feedback_entries")

    __table_args__ = (
        Index("idx_analyst_feedback_prediction_id", "prediction_id"),
        Index("idx_analyst_feedback_hotspot_id", "hotspot_id"),
        Index("idx_analyst_feedback_verified_class", "verified_class"),
    )
