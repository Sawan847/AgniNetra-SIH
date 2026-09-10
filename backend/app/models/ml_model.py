"""Model version model — ML model metadata and versioning."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Uuid
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ModelVersion(Base):
    """A versioned ML model with hyperparameters and metrics."""

    __tablename__ = "model_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    algorithm: Mapped[str] = mapped_column(
        String(50), nullable=False, doc="xgboost, random_forest, etc."
    )

    hyperparameters: Mapped[dict | None] = mapped_column(JSON)
    metrics: Mapped[dict | None] = mapped_column(
        JSON, doc="accuracy, f1, confusion_matrix, etc."
    )
    artifact_path: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    trained_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    predictions = relationship("Prediction", back_populates="model_version", lazy="dynamic")
