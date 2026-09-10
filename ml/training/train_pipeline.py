"""AgniNetra AI - Training pipeline over weakly-supervised real-format detections.

Replaces the previous synthetic-feature trainer. The distinction matters:

  OLD: features were generated per-class from hand-written distributions, so the
       classifier learned to invert the generator and the reported F1 measured
       nothing about real fires.

  NEW: detections carry no label. Features are computed from observed behaviour and
       real OSM geometry. Labels are derived by independent weak-supervision rules.
       The model must learn the mapping the same way it would on live FIRMS data.

Evaluation uses two splits, because either alone is misleading:

  Spatial GroupKFold on site_id - thermal detections are strongly autocorrelated in
      space. A random split puts detections from the same refinery in both train and
      test, and the model scores well by memorising that location rather than by
      learning what a flare looks like.

  Chronological holdout - the operational task is to classify tomorrow's detections
      from a model fitted on history, so the test set must lie in the future.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

from ml.features.site_features import SITE_FEATURE_COLUMNS, build_feature_frame
from ml.labeling.weak_labels import (
    TRAINED_CLASSES,
    apply_weak_labels,
    label_coverage_report,
)

logger = logging.getLogger(__name__)

ARTIFACTS_DIR = os.path.join("ml", "artifacts")

# Below this max class probability the model declines to commit and the detection is
# routed to the human verification queue instead of raising an alert. Abstention is a
# decision rule applied here, at inference - not a sixth class the model is trained
# to recognise. There is no such thing as a physically "uncertain" fire.
ABSTAIN_THRESHOLD = 0.55


def build_training_frame(
    detections: pd.DataFrame,
    facilities: Optional[List[Dict[str, Any]]] = None,
) -> pd.DataFrame:
    """Feature-engineer and weakly label a set of raw detections."""
    feats = build_feature_frame(detections, facilities=facilities)
    labelled = apply_weak_labels(feats)
    return labelled


def train(
    labelled: pd.DataFrame,
    artifacts_dir: str = ARTIFACTS_DIR,
    algorithms: Optional[List[str]] = None,
    data_provenance: str = "unspecified",
) -> Dict[str, Any]:
    """Fit, compare and serialise. Returns the training report."""
    os.makedirs(artifacts_dir, exist_ok=True)
    algorithms = algorithms or ["random_forest", "hist_gradient_boosting", "logistic_regression"]

    coverage = label_coverage_report(labelled)
    logger.info("Label coverage: %.1f%% (%d of %d)",
                coverage["coverage"] * 100, coverage["labelled"], coverage["total_detections"])

    # Unlabelled rows are excluded, never coerced into a class.
    train_pool = labelled[labelled["weak_label"].notna()].copy()
    if train_pool.empty:
        raise ValueError("No labelled rows - check labelling functions and OSM ingestion.")

    train_pool["_date"] = pd.to_datetime(train_pool["acq_date"])
    split_date = train_pool["_date"].quantile(0.80)
    tr = train_pool[train_pool["_date"] < split_date]
    te = train_pool[train_pool["_date"] >= split_date]

    if te.empty or tr.empty:
        raise ValueError("Chronological split produced an empty side.")

    X_tr = _matrix(tr)
    y_tr = tr["weak_label"].to_numpy()
    g_tr = tr["site_id"].to_numpy()
    X_te = _matrix(te)
    y_te = te["weak_label"].to_numpy()

    logger.info("Train %d rows / %d sites | Holdout %d rows (from %s)",
                len(tr), len(set(g_tr)), len(te), split_date.date())

    results: Dict[str, Any] = {}
    best_name, best_f1, best_model, best_scaler = None, -1.0, None, None

    for algo in algorithms:
        cv_scores = _spatial_cv(algo, X_tr, y_tr, g_tr)

        model, scaler = _fit(algo, X_tr, y_tr)
        preds = model.predict(_scale(scaler, X_te))
        holdout_f1 = float(f1_score(y_te, preds, average="macro", zero_division=0))

        results[algo] = {
            "spatial_cv_macro_f1_mean": round(float(np.mean(cv_scores)), 4),
            "spatial_cv_macro_f1_std": round(float(np.std(cv_scores)), 4),
            "spatial_cv_folds": [round(float(s), 4) for s in cv_scores],
            "temporal_holdout_macro_f1": round(holdout_f1, 4),
        }
        logger.info("%-24s spatialCV=%.4f+/-%.4f  holdout=%.4f", algo,
                    np.mean(cv_scores), np.std(cv_scores), holdout_f1)

        # Select on spatial CV, not on the holdout. Choosing the model that scores
        # best on the holdout turns that holdout into a validation set and the
        # reported number stops being an honest estimate of unseen performance.
        if np.mean(cv_scores) > best_f1:
            best_f1 = float(np.mean(cv_scores))
            best_name, best_model, best_scaler = algo, model, scaler

    final_preds = best_model.predict(_scale(best_scaler, X_te))
    final_probs = best_model.predict_proba(_scale(best_scaler, X_te))

    labels_present = sorted(set(y_te) | set(final_preds))
    report = classification_report(
        y_te, final_preds, labels=labels_present, output_dict=True, zero_division=0
    )
    cm = confusion_matrix(y_te, final_preds, labels=labels_present).tolist()

    max_prob = final_probs.max(axis=1)
    abstain_rate = float((max_prob < ABSTAIN_THRESHOLD).mean())
    confident = max_prob >= ABSTAIN_THRESHOLD
    f1_confident = (
        float(f1_score(y_te[confident], final_preds[confident], average="macro", zero_division=0))
        if confident.any() else 0.0
    )

    ablation = run_ablation(labelled, algo="random_forest")
    logger.info(
        "Ablation: all-features CV=%.4f -> withholding rule features CV=%.4f (delta %.4f)",
        ablation.get("spatial_cv_macro_f1_all_features", 0.0),
        ablation.get("spatial_cv_macro_f1_ablated", 0.0),
        ablation.get("delta", 0.0),
    )

    missing_cls = sorted(set(y_tr) - set(y_te))
    if missing_cls:
        logger.warning(
            "Chronological holdout is missing %d class(es): %s. Those are unscored "
            "in the holdout metric - rely on spatial CV for them.",
            len(missing_cls), ", ".join(missing_cls),
        )

    bundle = {
        "model": best_model,
        "scaler": best_scaler,
        "features": SITE_FEATURE_COLUMNS,
        "classes": list(best_model.classes_),
        "abstain_threshold": ABSTAIN_THRESHOLD,
    }
    model_path = os.path.join(artifacts_dir, "thermal_classifier.joblib")
    joblib.dump(bundle, model_path)

    card = {
        "model_name": "AgniNetra-ThermalClassifier",
        "version": "2.0.0",
        "algorithm": best_name,
        "trained_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "data_provenance": data_provenance,
        "label_source": "programmatic weak supervision (ml.labeling.weak_labels)",
        "classes": TRAINED_CLASSES,
        "n_features": len(SITE_FEATURE_COLUMNS),
        "features": SITE_FEATURE_COLUMNS,
        "label_coverage": coverage,
        "n_train_rows": int(len(tr)),
        "n_train_sites": int(len(set(g_tr))),
        "n_holdout_rows": int(len(te)),
        "holdout_from_date": str(split_date.date()),
        "validation_strategy": (
            "Spatial GroupKFold on DBSCAN site_id for model selection; "
            "chronological 20% holdout for the reported score. "
            "Model selected on CV, never on the holdout."
        ),
        "algorithm_comparison": results,
        "selected_model_metrics": {
            "temporal_holdout_macro_f1": round(
                float(f1_score(y_te, final_preds, average="macro", zero_division=0)), 4),
            "abstain_rate": round(abstain_rate, 4),
            "macro_f1_on_confident_subset": round(f1_confident, 4),
            "per_class": {
                k: {kk: round(float(vv), 4) for kk, vv in v.items()}
                for k, v in report.items() if isinstance(v, dict)
            },
            "confusion_matrix": {"labels": labels_present, "matrix": cm},
        },
        "label_circularity_note": (
            "The labelling functions key on dist_industrial_km, persistence_ratio, "
            "land_cover_class and is_nighttime, and those same features are given to "
            "the model. A near-perfect score on this setup therefore demonstrates that "
            "the model recovered the rules, NOT that it classifies real fires well. "
            "See feature_ablation for the score with those features withheld, which is "
            "the honest measure of independent signal."
        ),
        "feature_ablation": ablation,
        "holdout_class_coverage": {
            "classes_in_holdout": sorted(set(y_te)),
            "classes_missing_from_holdout": sorted(set(y_tr) - set(y_te)),
            "warning": (
                "Classes absent from the chronological holdout are unscored. Seasonal "
                "classes (agricultural burning, and incidents that happened to fall "
                "earlier in the series) can vanish from a date-based split entirely. "
                "Read the spatial CV score for those."
                if set(y_tr) - set(y_te) else "All trained classes present in holdout."
            ),
        },
        "known_limitations": [
            "Labels are weak, not hand-verified. Reported metrics measure agreement "
            "with the labelling functions, and inherit any bias those rules carry.",
            "A held-out set of manually verified sites is required before any claim "
            "of real-world accuracy.",
            "Spectral indices (NDVI/NBR/dNBR) are excluded from the feature set "
            "unless Google Earth Engine is configured; they are never imputed.",
            "burn_scar_within_30d requires a MODIS MCD64A1 join. Without it the "
            "highest-precision labelling function never fires.",
        ],
    }

    with open(os.path.join(artifacts_dir, "model_card.json"), "w", encoding="utf-8") as fh:
        json.dump(card, fh, indent=2)

    logger.info("Best: %s | spatial CV %.4f | artifacts -> %s", best_name, best_f1, artifacts_dir)
    return {"best_algorithm": best_name, "model_path": model_path, "card": card}


# The labelling functions key directly on these features. Because the model is
# trained on labels those rules produced, a model given all of them can score near
# 1.0 simply by re-deriving the rules - which proves nothing about real fires.
# Withholding them is the honest test of whether independent signal exists.
LABEL_DEFINING_FEATURES = [
    "dist_industrial_km",
    "dist_mine_km",
    "dist_landfill_km",
    "persistence_ratio",
    "land_cover_class",
    "is_nighttime",
]


def run_ablation(
    labelled: pd.DataFrame, algo: str = "random_forest"
) -> Dict[str, Any]:
    """Retrain without the features the labelling rules key on.

    Interpretation:
      score stays high  - the model found genuinely independent signal (thermal
                          behaviour, FRP dynamics, site persistence statistics) and
                          is doing more than memorising the rules.
      score collapses   - the model is a compression of the labelling functions.
                          Still operationally useful, but it must not be presented
                          as having learned anything the rules did not already encode.

    Either outcome is worth reporting. Reporting only the unablated 1.0 would be
    misleading.
    """
    pool = labelled[labelled["weak_label"].notna()].copy()
    if pool.empty:
        return {"error": "no labelled rows"}

    kept = [c for c in SITE_FEATURE_COLUMNS if c not in LABEL_DEFINING_FEATURES]
    X_full = _matrix(pool)
    X_abl = X_full[kept]
    y = pool["weak_label"].to_numpy()
    g = pool["site_id"].to_numpy()

    full_scores = _spatial_cv_on(algo, X_full, y, g)
    abl_scores = _spatial_cv_on(algo, X_abl, y, g)

    return {
        "algorithm": algo,
        "withheld_features": LABEL_DEFINING_FEATURES,
        "retained_features": kept,
        "spatial_cv_macro_f1_all_features": round(float(np.mean(full_scores)), 4),
        "spatial_cv_macro_f1_ablated": round(float(np.mean(abl_scores)), 4),
        "delta": round(float(np.mean(full_scores) - np.mean(abl_scores)), 4),
    }


def _spatial_cv_on(algo: str, X: pd.DataFrame, y: np.ndarray, groups: np.ndarray) -> List[float]:
    n_splits = int(min(5, len(set(groups))))
    if n_splits < 2:
        return [0.0]
    scores: List[float] = []
    for tr_i, va_i in GroupKFold(n_splits=n_splits).split(X, y, groups=groups):
        if len(set(y[tr_i])) < 2:
            continue
        model, scaler = _fit(algo, X.iloc[tr_i], y[tr_i])
        pred = model.predict(_scale(scaler, X.iloc[va_i]))
        scores.append(float(f1_score(y[va_i], pred, average="macro", zero_division=0)))
    return scores or [0.0]


def _spatial_cv(algo: str, X: pd.DataFrame, y: np.ndarray, groups: np.ndarray) -> List[float]:
    """GroupKFold on site_id so no site appears in both train and validation."""
    n_groups = len(set(groups))
    n_splits = int(min(5, n_groups))
    if n_splits < 2:
        return [0.0]

    scores: List[float] = []
    for tr_i, va_i in GroupKFold(n_splits=n_splits).split(X, y, groups=groups):
        # A fold that lost a whole class cannot be scored meaningfully.
        if len(set(y[tr_i])) < 2:
            continue
        model, scaler = _fit(algo, X.iloc[tr_i], y[tr_i])
        pred = model.predict(_scale(scaler, X.iloc[va_i]))
        scores.append(float(f1_score(y[va_i], pred, average="macro", zero_division=0)))
    return scores or [0.0]


def _fit(algo: str, X: pd.DataFrame, y: np.ndarray):
    scaler = None
    Xv = X.to_numpy(dtype=np.float64)
    if algo == "logistic_regression":
        scaler = StandardScaler().fit(Xv)
        Xv = scaler.transform(Xv)
        model = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42)
    elif algo == "hist_gradient_boosting":
        model = HistGradientBoostingClassifier(
            max_iter=200, max_depth=6, learning_rate=0.08,
            class_weight="balanced", random_state=42)
    else:
        model = RandomForestClassifier(
            n_estimators=300, max_depth=14, min_samples_leaf=2,
            class_weight="balanced_subsample", n_jobs=-1, random_state=42)
    model.fit(Xv, y)
    return model, scaler


def _scale(scaler, X: pd.DataFrame) -> np.ndarray:
    Xv = X.to_numpy(dtype=np.float64)
    return scaler.transform(Xv) if scaler is not None else Xv


def _matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Select the feature columns, adding any that are missing as zeros.

    Missing columns are filled rather than raising, because a partially-configured
    deployment (no GEE, no MCD64A1) should still run. What must never happen is
    filling a column with a *plausible-looking* value - that is imputation
    masquerading as measurement.
    """
    out = df.copy()
    for col in SITE_FEATURE_COLUMNS:
        if col not in out.columns:
            logger.warning("Feature %s absent - filling with 0.0", col)
            out[col] = 0.0
    return out[SITE_FEATURE_COLUMNS].fillna(0.0)


def predict_with_abstention(
    bundle: Dict[str, Any], features: pd.DataFrame
) -> List[Dict[str, Any]]:
    """Score detections, abstaining where the model is not confident enough."""
    model, scaler = bundle["model"], bundle["scaler"]
    thresh = bundle.get("abstain_threshold", ABSTAIN_THRESHOLD)
    classes = list(model.classes_)

    X = _matrix(features)
    probs = model.predict_proba(_scale(scaler, X))

    results = []
    for row in probs:
        top = int(np.argmax(row))
        p = float(row[top])
        results.append({
            "predicted_class": classes[top] if p >= thresh else "uncertain",
            "confidence": round(p, 4),
            "requires_human_review": bool(p < thresh),
            "class_probabilities": {c: round(float(v), 4) for c, v in zip(classes, row)},
        })
    return results
