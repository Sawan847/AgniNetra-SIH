"""Unit and integration tests for ML Classifier and training pipeline."""

from __future__ import annotations

import numpy as np
import pandas as pd
from ml.config import FIRE_CLASSES, FEATURE_COLUMNS
from ml.models.classifier import ThermalFireClassifier
from ml.models.two_stage import TwoStageThermalClassifier
from ml.training.train import generate_synthetic_training_data, run_model_comparison_and_training


def test_synthetic_data_generation():
    X, y, groups = generate_synthetic_training_data(n_samples=120, random_state=42)
    assert len(X) == 120
    assert len(y) == 120
    assert len(groups) == 120
    assert set(y.unique()) == set(FIRE_CLASSES)
    assert "brightness" in X.columns
    assert "dist_nearest_facility" in X.columns
    assert "persistence_score" in X.columns
    # Verify groups are integers for GroupKFold
    assert groups.dtype in (np.int32, np.int64, int)


def test_legacy_classifier_fit_predict():
    """Verify the original single-stage ThermalFireClassifier still works."""
    X, y, _groups = generate_synthetic_training_data(n_samples=180, random_state=42)
    # Drop non-feature columns before fitting
    X_features = X.drop(columns=["acq_date", "latitude", "longitude"], errors="ignore")
    clf = ThermalFireClassifier(use_xgboost=False)
    clf.fit(X_features, y)

    preds = clf.predict(X_features[:10])
    assert len(preds) == 10
    for p in preds:
        assert p in FIRE_CLASSES

    probas = clf.predict_proba(X_features[:5])
    assert probas.shape == (5, len(FIRE_CLASSES))
    assert np.allclose(probas.sum(axis=1), 1.0)


def test_legacy_classifier_predict_detailed():
    X, y, _groups = generate_synthetic_training_data(n_samples=120, random_state=42)
    X_features = X.drop(columns=["acq_date", "latitude", "longitude"], errors="ignore")
    clf = ThermalFireClassifier(use_xgboost=False)
    clf.fit(X_features, y)

    detailed = clf.predict_detailed(X_features[:3])
    assert len(detailed) == 3
    for res in detailed:
        assert "predicted_class" in res
        assert "confidence_score" in res
        assert "class_probabilities" in res
        assert 0.0 <= res["confidence_score"] <= 1.0


def test_two_stage_classifier():
    """Verify the new TwoStageThermalClassifier fit/predict pipeline."""
    X, y, _groups = generate_synthetic_training_data(n_samples=300, random_state=42)
    X_features = X.drop(columns=["acq_date", "latitude", "longitude"], errors="ignore")

    clf = TwoStageThermalClassifier(algorithm="random_forest", calibrate=False)
    clf.fit(X_features, y)

    preds = clf.predict(X_features[:10])
    assert len(preds) == 10
    for p in preds:
        assert p in FIRE_CLASSES or p == "uncertain"

    probas = clf.predict_proba(X_features[:5])
    assert probas.shape == (5, len(FIRE_CLASSES))
    # Probabilities should sum to ~1
    for row_sum in probas.sum(axis=1):
        assert abs(row_sum - 1.0) < 0.05

    detailed = clf.predict_detailed(X_features[:3])
    assert len(detailed) == 3
    for res in detailed:
        assert "predicted_class" in res
        assert "confidence_score" in res
        assert "stage1_class" in res
        assert "explanation" in res


def test_training_pipeline():
    """Verify run_model_comparison_and_training produces valid artifacts."""
    import tempfile
    import os

    X, y, groups = generate_synthetic_training_data(n_samples=300, random_state=42)
    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_model_comparison_and_training(X, y, groups, artifacts_dir=tmpdir)

        assert "best_algorithm" in result
        assert "best_macro_f1" in result
        assert "comparison" in result
        assert result["best_macro_f1"] > 0.0

        # Verify artifacts were saved
        assert os.path.exists(result["artifact_path"])
        assert os.path.exists(result["model_card_path"])
        assert os.path.exists(result["schema_path"])


def test_feature_column_alignment():
    """Ensure synthetic data features match FEATURE_COLUMNS from ml.config."""
    X, y, _groups = generate_synthetic_training_data(n_samples=60, random_state=42)
    X_features = X.drop(columns=["acq_date", "latitude", "longitude"], errors="ignore")
    for col in FEATURE_COLUMNS:
        assert col in X_features.columns, f"Missing expected feature column: {col}"
