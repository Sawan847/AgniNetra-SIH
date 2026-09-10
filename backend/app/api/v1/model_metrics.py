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
    """Return metrics for the model that is actually loaded and serving predictions.

    The model card written by ml.training.train_pipeline is the SOURCE OF TRUTH, and
    is read first. The database ModelVersion table is only consulted if no card
    exists on disk.

    The order used to be reversed, and that was actively misleading: seed_demo.py
    inserts a ModelVersion row describing a two-stage XGBoost model with 37 features
    and a 93.8% F1, none of which corresponds to anything. Those invented figures
    were served to the dashboard and displayed as the live model's performance,
    contradicting the real metrics sitting in model_card.json.
    """
    artifacts_dir = os.environ.get("ML_ARTIFACTS_DIR", "ml/artifacts")
    model_card_path = os.path.join(artifacts_dir, "model_card.json")

    if os.path.exists(model_card_path):
        with open(model_card_path, "r", encoding="utf-8") as f:
            model_card: Dict[str, Any] = json.load(f)

        selected = model_card.get("selected_model_metrics", {}) or {}
        comparison = model_card.get("algorithm_comparison", {}) or {}
        chosen = model_card.get("algorithm", "")
        chosen_cv = comparison.get(chosen, {}) or {}

        # Flatten the figures the dashboard tiles read, keeping the names the
        # frontend already expects.
        evaluation_metrics: Dict[str, Any] = {
            "macro_f1": selected.get("temporal_holdout_macro_f1"),
            "mean_spatial_cv_f1": chosen_cv.get("spatial_cv_macro_f1_mean"),
            "abstain_rate": selected.get("abstain_rate"),
            "macro_f1_on_confident_subset": selected.get("macro_f1_on_confident_subset"),
            "per_class": selected.get("per_class", {}),
            "confusion_matrix": selected.get("confusion_matrix", {}),
            "n_features": model_card.get("n_features"),
            "classes": model_card.get("classes", []),
            "data_provenance": model_card.get("data_provenance"),
            "label_coverage": model_card.get("label_coverage", {}),
            "feature_ablation": model_card.get("feature_ablation", {}),
            "holdout_class_coverage": model_card.get("holdout_class_coverage", {}),
            "label_circularity_note": model_card.get("label_circularity_note"),
            "known_limitations": model_card.get("known_limitations", []),
        }

        return ModelMetricsResponse(
            active_model_name=model_card.get("model_name", "AgniNetra-ThermalClassifier"),
            algorithm=chosen or "unknown",
            version=model_card.get("version", "0.0.0"),
            evaluation_metrics=evaluation_metrics,
            feature_importances={},
            model_card=model_card,
        )

    # No artifact on disk. Fall back to the registry table.
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

    # Nothing trained yet. Report that plainly rather than inventing a model.
    return ModelMetricsResponse(
        active_model_name="No model trained",
        algorithm="none",
        version="0.0.0",
        evaluation_metrics={},
        feature_importances={},
        model_card=None,
    )
