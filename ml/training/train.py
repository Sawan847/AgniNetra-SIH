"""DEPRECATED - superseded by ml.training.train_pipeline.

DO NOT USE FOR TRAINING. Retained only so older imports keep resolving.

Why this was retired
--------------------
generate_synthetic_training_data() below produces the *feature vector* for each
class from hand-written per-class distributions - dist_nearest_facility, frp,
persistence_score and the rest are all drawn from ranges chosen to match the label.
A classifier trained on that data learns to invert those if-statements, and the
macro-F1 it reports measures how well scikit-learn can reverse-engineer the
generator. It says nothing about real fires.

Two further defects made it worse than merely uninformative:

  * load_classifier_pipeline() trained on this synthetic data on first call when no
    artifact existed - so a live API endpoint would fit a model to fiction and then
    serve it in production.

  * The generator sampled cluster_size, cluster_spread_km and cluster_direction_deg
    randomly, while the inference path hardcoded them to 1.0/0.0/0.0. Three features
    the model learned from were frozen constants in production.

The replacement
---------------
ml.training.train_pipeline trains on detections that carry no label. Features come
from observed behaviour and real OSM geometry; labels are derived independently by
ml.labeling.weak_labels. Run it via:

    python scripts/build_dataset.py --source sim      # offline
    python scripts/build_dataset.py --source firms    # live NASA FIRMS

Original docstring follows.

---

AgniNetra AI - Machine Learning Training & Model Comparison Pipeline.

Features:
- Geographic Group-based train/validation splitting (GroupKFold)
- Time-based final holdout evaluation (preventing temporal leakage)
- Class-imbalance handling applied strictly to training data
- Automated comparison of Logistic Regression, Random Forest, HistGradientBoosting, and XGBoost
- Serialization of best two-stage pipeline, Model Card, and Feature Schema
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from ml.config import FEATURE_COLUMNS, FIRE_CLASSES
from ml.evaluation.metrics import evaluate_classification
from ml.models.two_stage import TwoStageThermalClassifier

logger = logging.getLogger(__name__)


def generate_synthetic_training_data(
    n_samples: int = 1200,
    random_state: int = 42,
) -> Tuple[pd.DataFrame, pd.Series, np.ndarray]:
    """Generate demonstration training dataset with spatial coordinates, temporal dates, and geographic regions.

    Returns: (X_dataframe, y_series, spatial_groups)
    """
    rng = np.random.default_rng(random_state)
    samples_per_class = n_samples // len(FIRE_CLASSES)

    records = []
    labels = []
    groups = []

    # 10 distinct geographic regions across India for GroupKFold
    regions = [
        ("Gujarat_West", 22.4, 70.0),
        ("Haryana_Punjab", 29.8, 76.5),
        ("Chhattisgarh_Mining", 22.3, 82.5),
        ("Jharkhand_Industrial", 22.8, 86.2),
        ("Maharashtra_Central", 19.5, 75.5),
        ("Odisha_Mines", 21.5, 85.0),
        ("TamilNadu_South", 11.0, 78.0),
        ("MadhyaPradesh_Forest", 23.2, 79.8),
        ("Rajasthan_West", 26.5, 72.0),
        ("Assam_Northeast", 26.2, 92.8),
    ]

    base_date = datetime.date(2024, 1, 1)

    for class_idx, fire_class in enumerate(FIRE_CLASSES):
        for s_idx in range(samples_per_class):
            region_idx = (class_idx + s_idx) % len(regions)
            reg_name, reg_lat, reg_lon = regions[region_idx]

            # Date distribution over 250 days
            day_offset = int(rng.integers(0, 250))
            curr_date = base_date + datetime.timedelta(days=day_offset)

            lat = float(reg_lat + rng.normal(0, 0.2))
            lon = float(reg_lon + rng.normal(0, 0.2))

            if fire_class == "accidental_industrial_fire":
                dist_fac = float(rng.exponential(0.2))
                is_inside = 1.0 if dist_fac < 0.15 else 0.0
                frp = float(rng.uniform(120.0, 600.0))
                bright_ti4 = float(rng.uniform(360.0, 440.0))
                p_score = float(rng.uniform(0.0, 2.0))
                hist_med = float(rng.uniform(20.0, 60.0))
                d_nbr = float(rng.uniform(0.15, 0.45))
                cover = 50  # built-up
                is_night = int(rng.choice([0, 1]))
            elif fire_class == "persistent_industrial_source":
                dist_fac = float(rng.uniform(0.01, 0.15))
                is_inside = 1.0
                frp = float(rng.uniform(25.0, 95.0))
                bright_ti4 = float(rng.uniform(330.0, 375.0))
                p_score = float(rng.uniform(5.0, 25.0))
                hist_med = float(frp * rng.uniform(0.8, 1.2))
                d_nbr = float(rng.uniform(0.0, 0.08))
                cover = 50
                is_night = 1
            elif fire_class == "forest_or_natural_fire":
                dist_fac = float(rng.uniform(8.0, 50.0))
                is_inside = 0.0
                frp = float(rng.uniform(150.0, 900.0))
                bright_ti4 = float(rng.uniform(350.0, 480.0))
                p_score = float(rng.uniform(0.0, 2.0))
                hist_med = float(rng.uniform(10.0, 40.0))
                d_nbr = float(rng.uniform(0.35, 0.80))
                cover = 10  # tree cover
                is_night = int(rng.choice([0, 1]))
            elif fire_class == "agricultural_burning":
                dist_fac = float(rng.uniform(3.0, 30.0))
                is_inside = 0.0
                frp = float(rng.uniform(10.0, 55.0))
                bright_ti4 = float(rng.uniform(315.0, 345.0))
                p_score = float(rng.uniform(0.0, 1.0))
                hist_med = float(rng.uniform(5.0, 25.0))
                d_nbr = float(rng.uniform(0.10, 0.30))
                cover = 40  # cropland
                is_night = 0
            elif fire_class == "mining_or_other":
                dist_fac = float(rng.uniform(0.5, 4.0))
                is_inside = 0.0
                frp = float(rng.uniform(35.0, 180.0))
                bright_ti4 = float(rng.uniform(320.0, 365.0))
                p_score = float(rng.uniform(2.0, 8.0))
                hist_med = float(rng.uniform(30.0, 90.0))
                d_nbr = float(rng.uniform(0.01, 0.10))
                cover = 60  # bare/mine
                is_night = int(rng.choice([0, 1]))
            else:  # uncertain
                dist_fac = float(rng.uniform(0.2, 15.0))
                is_inside = float(rng.choice([0.0, 1.0]))
                frp = float(rng.uniform(15.0, 150.0))
                bright_ti4 = float(rng.uniform(310.0, 370.0))
                p_score = float(rng.uniform(0.0, 4.0))
                hist_med = float(rng.uniform(15.0, 60.0))
                d_nbr = float(rng.uniform(0.05, 0.20))
                cover = int(rng.choice([10, 20, 30, 40, 50, 60]))
                is_night = int(rng.choice([0, 1]))

            bright_ti5 = float(bright_ti4 - rng.uniform(10.0, 25.0))
            ratio_frp = round(frp / (hist_med + 1e-3), 2)

            row = {
                "latitude": lat,
                "longitude": lon,
                "acq_date": curr_date,
                "brightness": round(bright_ti4, 2),
                "bright_ti4": round(bright_ti4, 2),
                "bright_ti5": round(bright_ti5, 2),
                "brightness_delta": round(bright_ti4 - bright_ti5, 2),
                "frp": round(frp, 2),
                "confidence": round(float(rng.uniform(65.0, 98.0)), 1),
                "is_nighttime": float(is_night),
                "day_of_year": float(curr_date.timetuple().tm_yday),
                "dist_nearest_facility": round(dist_fac, 3),
                "is_inside_facility": is_inside,
                "nearby_facility_count_1km": 3.0 if dist_fac < 0.5 else 0.0,
                "nearby_facility_count_5km": 8.0 if dist_fac < 3.0 else 1.0,
                "dist_nearest_forest": 0.2 if cover == 10 else 6.0,
                "dist_nearest_cropland": 0.1 if cover == 40 else 3.0,
                "dist_nearest_mine": 0.1 if cover == 60 else 10.0,
                "dist_nearest_settlement": 0.5 if is_inside else 4.0,
                "nearby_hotspot_count_24h": float(rng.poisson(2)),
                "nearby_hotspot_count_7d": float(p_score + rng.poisson(1)),
                "nearby_hotspot_count_30d": float(p_score * 3 + rng.poisson(3)),
                "nearby_hotspot_count_90d": float(p_score * 8 + rng.poisson(5)),
                "persistence_score": round(p_score, 2),
                "persistence_score_30d": round(p_score * 3, 2),
                "recurrence_rate": round(p_score / 7.0, 3),
                "historical_median_frp": round(hist_med, 2),
                "historical_max_frp": round(hist_med * 1.5, 2),
                "frp_to_historical_ratio": ratio_frp,
                "cluster_size": float(rng.choice([1, 2, 4, 8])),
                "cluster_spread_km": round(float(rng.uniform(0.0, 2.5)), 3),
                "cluster_direction_deg": round(float(rng.uniform(0.0, 360.0)), 1),
                "spatial_density_5km": round(float(rng.uniform(0.01, 0.25)), 4),
                "land_cover_class": float(cover),
                "ndvi_value": round(float(rng.uniform(0.10, 0.75)), 3),
                "nbr_value": round(float(rng.uniform(0.05, 0.65)), 3),
                "ndmi_value": round(float(rng.uniform(-0.10, 0.40)), 3),
                "delta_nbr": round(d_nbr, 3),
                "cloud_cover_fraction": round(float(rng.uniform(0.0, 0.20)), 2),
                "imagery_available": 1.0,
            }
            records.append(row)
            labels.append(fire_class)
            groups.append(region_idx)

    df_X = pd.DataFrame(records)
    s_y = pd.Series(labels, name="fire_class")
    return df_X, s_y, np.array(groups)


def run_model_comparison_and_training(
    X: pd.DataFrame,
    y: pd.Series,
    groups: np.ndarray,
    artifacts_dir: str = "ml/artifacts",
) -> Dict[str, Any]:
    """Train, cross-validate with geographic grouping, evaluate on temporal holdout, and compare algorithms."""
    os.makedirs(artifacts_dir, exist_ok=True)

    # 1. Temporal Holdout Split (Holdout latest 15% dates)
    dates = pd.to_datetime(X["acq_date"])
    split_date = dates.quantile(0.85)

    train_idx = np.where(dates < split_date)[0]
    test_idx = np.where(dates >= split_date)[0]

    X_train_df = X.iloc[train_idx].drop(columns=["acq_date", "latitude", "longitude"], errors="ignore")
    y_train = y.iloc[train_idx].values
    groups_train = groups[train_idx]

    X_test_df = X.iloc[test_idx].drop(columns=["acq_date", "latitude", "longitude"], errors="ignore")
    y_test = y.iloc[test_idx].values

    algorithms = ["random_forest", "hist_gradient_boosting", "logistic_regression"]
    from ml.models.two_stage import XGB_AVAILABLE
    if XGB_AVAILABLE:
        algorithms.insert(0, "xgboost")

    comparison_results = {}
    best_algo = "random_forest"
    best_f1 = -1.0
    best_model: Optional[TwoStageThermalClassifier] = None
    best_metrics: Optional[Dict[str, Any]] = None

    # Group K-Fold Cross Validation on Spatial Regions
    gkf = GroupKFold(n_splits=min(5, len(np.unique(groups_train))))

    for algo in algorithms:
        cv_f1_scores = []
        for fold_train, fold_val in gkf.split(X_train_df, y_train, groups=groups_train):
            clf = TwoStageThermalClassifier(algorithm=algo, calibrate=False)
            clf.fit(X_train_df.iloc[fold_train], y_train[fold_train])
            val_preds = clf.predict(X_train_df.iloc[fold_val])
            val_eval = evaluate_classification(y_train[fold_val], val_preds, classes=FIRE_CLASSES)
            cv_f1_scores.append(val_eval["macro_f1"])

        mean_cv_f1 = float(np.mean(cv_f1_scores))

        # Train full model with probability calibration
        full_model = TwoStageThermalClassifier(algorithm=algo, calibrate=True)
        full_model.fit(X_train_df, y_train)

        # Evaluate on unseen temporal holdout
        test_preds = full_model.predict(X_test_df)
        test_probas = full_model.predict_proba(X_test_df)
        test_metrics = evaluate_classification(y_test, test_preds, test_probas, classes=FIRE_CLASSES)
        test_metrics["mean_spatial_cv_f1"] = round(mean_cv_f1, 4)

        # Calculate false alert rate on industrial fire
        cm = np.array(test_metrics["confusion_matrix"])
        # Index 0 is accidental_industrial_fire
        ind_fire_idx = 0
        fp = float(cm[:, ind_fire_idx].sum() - cm[ind_fire_idx, ind_fire_idx])
        tn = float(cm.sum() - cm[ind_fire_idx, :].sum() - cm[:, ind_fire_idx].sum() + cm[ind_fire_idx, ind_fire_idx])
        false_alert_rate = round(fp / (fp + tn + 1e-6), 4)
        test_metrics["false_alert_rate_industrial_fire"] = false_alert_rate

        comparison_results[algo] = {
            "spatial_cv_macro_f1": round(mean_cv_f1, 4),
            "holdout_accuracy": test_metrics["accuracy"],
            "holdout_macro_f1": test_metrics["macro_f1"],
            "holdout_weighted_f1": test_metrics["weighted_f1"],
            "false_alert_rate": false_alert_rate,
        }

        if test_metrics["macro_f1"] > best_f1:
            best_f1 = test_metrics["macro_f1"]
            best_algo = algo
            best_model = full_model
            best_metrics = test_metrics

    logger.info("Best Algorithm: %s with Holdout Macro F1: %.4f", best_algo, best_f1)

    # 2. Serialize Best Pipeline Artifact
    artifact_path = os.path.join(artifacts_dir, "fire_classifier.joblib")
    joblib.dump(best_model, artifact_path)

    # 3. Save Model Card
    model_card = {
        "model_name": f"AgniNetra-TwoStage-{best_algo.upper()}",
        "version": "1.1.0",
        "description": "Two-stage hierarchical classifier for industrial thermal anomalies, wildfires, stubble burning, and mining.",
        "algorithm": best_algo,
        "features_count": len(FEATURE_COLUMNS),
        "target_classes": FIRE_CLASSES,
        "evaluation_metrics": best_metrics,
        "algorithm_comparison": comparison_results,
        "validation_strategy": "Spatial GroupKFold + Chronological 15% Holdout",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "uncertainty_threshold": 0.45,
        "data_leakage_safeguards": [
            "Geographic grouping on coordinates to prevent spatial autocorrelation leakage",
            "Strict chronological holdout split on acquisition date",
            "Feature scaling and balancing fit strictly on training splits",
        ],
    }
    model_card_path = os.path.join(artifacts_dir, "model_card.json")
    with open(model_card_path, "w", encoding="utf-8") as f:
        json.dump(model_card, f, indent=2)

    # 4. Save Feature Schema
    schema_dict = {
        "features": [
            {"name": col, "dtype": "float32", "required": True}
            for col in FEATURE_COLUMNS
        ],
        "classes": FIRE_CLASSES,
        "stage1_classes": ["industrial", "forest_or_natural_fire", "agricultural_burning", "mining_or_other"],
        "stage2_classes": ["persistent_industrial_source", "accidental_industrial_fire"],
    }
    schema_path = os.path.join(artifacts_dir, "feature_schema.json")
    with open(schema_path, "w", encoding="utf-8") as f:
        json.dump(schema_dict, f, indent=2)

    return {
        "best_algorithm": best_algo,
        "best_macro_f1": best_f1,
        "metrics": best_metrics,
        "comparison": comparison_results,
        "artifact_path": artifact_path,
        "model_card_path": model_card_path,
        "schema_path": schema_path,
    }


def load_classifier_pipeline(
    artifact_path: str = "ml/artifacts/fire_classifier.joblib",
) -> TwoStageThermalClassifier:
    """DEPRECATED. Use app.services.classifier.classifier_service instead.

    This no longer trains on demand. Fitting a model inside a request handler - on
    synthetic data, no less - meant a production endpoint silently served a
    classifier fitted to fiction. Failing loudly is the correct behaviour.
    """
    warnings.warn(
        "ml.training.train.load_classifier_pipeline is deprecated; use "
        "app.services.classifier.classifier_service (backed by "
        "ml.training.train_pipeline).",
        DeprecationWarning,
        stacklevel=2,
    )
    if os.path.exists(artifact_path):
        return joblib.load(artifact_path)

    raise FileNotFoundError(
        f"No model artifact at {artifact_path}, and on-demand training on synthetic "
        "data has been removed. Build a real model first:\n"
        "    python scripts/build_dataset.py --source sim\n"
        "then load it via app.services.classifier.classifier_service."
    )
