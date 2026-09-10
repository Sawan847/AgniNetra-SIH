"""Model metrics endpoint — active model metadata, evaluation metrics, and feature importances."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.ml_model import ModelVersion
from app.schemas.system import ModelMetricsResponse

router = APIRouter()


@router.get("/model/metrics", response_model=ModelMetricsResponse)
def get_model_metrics(
    db: Session = Depends(get_db),
) -> ModelMetricsResponse:
    """Return active model version metadata, evaluation metrics, and feature importances."""

    # Try database first
    active_model = (
        db.query(ModelVersion)
        .filter(ModelVersion.is_active.is_(True))
        .order_by(ModelVersion.trained_at.desc())
        .first()
    )

    if active_model:
        feature_importances: Dict[str, float] = {}
        if active_model.metrics and "feature_importances" in active_model.metrics:
            feature_importances = active_model.metrics["feature_importances"]

        return ModelMetricsResponse(
            active_model_name=active_model.model_name,
            algorithm=active_model.algorithm,
            version=active_model.version,
            evaluation_metrics=active_model.metrics or {},
            feature_importances=feature_importances,
            model_card=None,
        )

    # Fall back to model_card.json artifact on disk
    artifacts_dir = os.environ.get("ML_ARTIFACTS_DIR", "ml/artifacts")
    model_card_path = os.path.join(artifacts_dir, "model_card.json")
    model_card: Optional[Dict[str, Any]] = None
    evaluation_metrics: Dict[str, Any] = {}
    feature_importances = {}
    model_name = "AgniNetra-TwoStage"
    algorithm = "unknown"
    version = "0.0.0"

    if os.path.exists(model_card_path):
        with open(model_card_path, "r", encoding="utf-8") as f:
            model_card = json.load(f)
        model_name = model_card.get("model_name", model_name)
        algorithm = model_card.get("algorithm", algorithm)
        version = model_card.get("version", version)
        evaluation_metrics = model_card.get("evaluation_metrics", {})

    return ModelMetricsResponse(
        active_model_name=model_name,
        algorithm=algorithm,
        version=version,
        evaluation_metrics=evaluation_metrics,
        feature_importances=feature_importances,
        model_card=model_card,
    )
