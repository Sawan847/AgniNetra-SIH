"""AgniNetra AI — Two-Stage Hybrid Classifier.

Stage 1: Classifies macro domain (industrial, forest/natural, agricultural, mining/other).
Stage 2: For industrial candidates, classifies persistent normal source vs accidental industrial fire.
Calibrates probabilities and applies an uncertainty threshold.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple
import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from ml.config import (
    DEFAULT_HGB_PARAMS,
    DEFAULT_LR_PARAMS,
    DEFAULT_RF_PARAMS,
    DEFAULT_XGBOOST_PARAMS,
    FEATURE_COLUMNS,
    FIRE_CLASSES,
    STAGE1_CLASSES,
    STAGE2_CLASSES,
)

logger = logging.getLogger(__name__)

# Check XGBoost availability
try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False


class TwoStageThermalClassifier(BaseEstimator, ClassifierMixin):
    """Production two-stage hierarchical classifier for thermal intelligence."""

    def __init__(
        self,
        algorithm: str = "random_forest",
        uncertain_threshold: float = 0.45,
        calibrate: bool = True,
        features: Optional[List[str]] = None,
    ):
        self.algorithm = algorithm.lower()
        self.uncertain_threshold = uncertain_threshold
        self.calibrate = calibrate
        self.features = features or FEATURE_COLUMNS

        self.stage1_model: Any = None
        self.stage2_model: Any = None
        self.scaler: Optional[StandardScaler] = None

        self.stage1_classes = STAGE1_CLASSES
        self.stage2_classes = STAGE2_CLASSES
        self.final_classes = FIRE_CLASSES

        self._s1_class_to_idx = {c: i for i, c in enumerate(self.stage1_classes)}
        self._s2_class_to_idx = {c: i for i, c in enumerate(self.stage2_classes)}
        self._s1_encoder: Any = None
        self._s2_encoder: Any = None

    def fit(self, X: pd.DataFrame, y: pd.Series | np.ndarray) -> TwoStageThermalClassifier:
        """Fit Stage 1 and Stage 2 models on labeled training dataset."""
        from sklearn.preprocessing import LabelEncoder

        X_mat = self._prepare_matrix(X, is_training=True)
        y_raw = np.asarray(y)

        # Map 6 classes to Stage 1 classes:
        # accidental_industrial_fire & persistent_industrial_source -> 'industrial'
        y_stage1_str = np.array([
            "industrial" if lbl in ("accidental_industrial_fire", "persistent_industrial_source")
            else (lbl if lbl in self.stage1_classes else "industrial")
            for lbl in y_raw
        ])

        # XGBoost v2+ requires integer labels — encode them
        if self.algorithm == "xgboost":
            self._s1_encoder = LabelEncoder()
            y_stage1_fit = self._s1_encoder.fit_transform(y_stage1_str)
        else:
            self._s1_encoder = None
            y_stage1_fit = y_stage1_str

        # Stage 1 Model instantiation & fitting
        base_s1 = self._instantiate_base_model(self.algorithm, n_classes=len(self.stage1_classes))
        if self.calibrate and len(np.unique(y_stage1_str)) >= 2:
            self.stage1_model = CalibratedClassifierCV(estimator=base_s1, cv=3, method="sigmoid")
        else:
            self.stage1_model = base_s1
        self.stage1_model.fit(X_mat, y_stage1_fit)

        # Filter industrial samples for Stage 2
        ind_mask = np.isin(y_raw, ["accidental_industrial_fire", "persistent_industrial_source"])
        if ind_mask.sum() >= 10 and len(np.unique(y_raw[ind_mask])) >= 2:
            X_ind = X_mat[ind_mask]
            y_ind_str = y_raw[ind_mask]
            if self.algorithm == "xgboost":
                self._s2_encoder = LabelEncoder()
                y_ind_fit = self._s2_encoder.fit_transform(y_ind_str)
            else:
                self._s2_encoder = None
                y_ind_fit = y_ind_str
            base_s2 = self._instantiate_base_model(self.algorithm, n_classes=len(self.stage2_classes))
            if self.calibrate:
                self.stage2_model = CalibratedClassifierCV(estimator=base_s2, cv=3, method="sigmoid")
            else:
                self.stage2_model = base_s2
            self.stage2_model.fit(X_ind, y_ind_fit)
        else:
            logger.info("Insufficient Stage 2 industrial labels (%d samples). Using default prior.", ind_mask.sum())
            self.stage2_model = None
            self._s2_encoder = None

        return self


    def predict_detailed(self, X: pd.DataFrame) -> List[Dict[str, Any]]:
        """Predict top class, combined probability distribution across all 6 classes, and stage info."""
        X_mat = self._prepare_matrix(X, is_training=False)
        n_samples = len(X_mat)

        # Stage 1 probabilities
        s1_probas = self.stage1_model.predict_proba(X_mat)
        if getattr(self, "_s1_encoder", None) is not None:
            s1_class_map = {self._s1_encoder.inverse_transform([c])[0]: i for i, c in enumerate(self.stage1_model.classes_)}
        else:
            s1_class_map = {c: i for i, c in enumerate(self.stage1_model.classes_)}

        results = []
        for i in range(n_samples):
            # Extract stage 1 probs
            p_ind = float(s1_probas[i, s1_class_map.get("industrial", 0)]) if "industrial" in s1_class_map else 0.0
            p_forest = float(s1_probas[i, s1_class_map.get("forest_or_natural_fire", 0)]) if "forest_or_natural_fire" in s1_class_map else 0.0
            p_agri = float(s1_probas[i, s1_class_map.get("agricultural_burning", 0)]) if "agricultural_burning" in s1_class_map else 0.0
            p_mining = float(s1_probas[i, s1_class_map.get("mining_or_other", 0)]) if "mining_or_other" in s1_class_map else 0.0

            # Stage 2 breakdown of industrial probability
            p_accidental = 0.0
            p_persistent = 0.0
            s2_class_pred = None

            if self.stage2_model is not None and p_ind > 0.01:
                s2_probas = self.stage2_model.predict_proba(X_mat[i : i + 1])[0]
                if getattr(self, "_s2_encoder", None) is not None:
                    s2_map = {self._s2_encoder.inverse_transform([c])[0]: idx for idx, c in enumerate(self.stage2_model.classes_)}
                else:
                    s2_map = {c: idx for idx, c in enumerate(self.stage2_model.classes_)}
                p_acc_given_ind = float(s2_probas[s2_map.get("accidental_industrial_fire", 0)]) if "accidental_industrial_fire" in s2_map else 0.5
                p_per_given_ind = float(s2_probas[s2_map.get("persistent_industrial_source", 0)]) if "persistent_industrial_source" in s2_map else 0.5

                p_accidental = p_ind * p_acc_given_ind
                p_persistent = p_ind * p_per_given_ind
                s2_class_pred = "accidental_industrial_fire" if p_acc_given_ind >= p_per_given_ind else "persistent_industrial_source"
            else:
                # Default heuristic prior based on persistence and FRP ratio
                dist_fac = float(X.iloc[i].get("dist_nearest_facility", 999.0))
                p_score = float(X.iloc[i].get("persistence_score", 0.0))
                frp = float(X.iloc[i].get("frp", 20.0))

                if dist_fac <= 0.2 and p_score >= 2.0 and frp < 150.0:
                    p_persistent = p_ind * 0.85
                    p_accidental = p_ind * 0.15
                    s2_class_pred = "persistent_industrial_source"
                else:
                    p_accidental = p_ind * 0.70
                    p_persistent = p_ind * 0.30
                    s2_class_pred = "accidental_industrial_fire"

            # Raw 5 non-uncertain class distribution
            raw_dist = {
                "accidental_industrial_fire": round(p_accidental, 4),
                "persistent_industrial_source": round(p_persistent, 4),
                "forest_or_natural_fire": round(p_forest, 4),
                "agricultural_burning": round(p_agri, 4),
                "mining_or_other": round(p_mining, 4),
            }

            # Top candidate
            top_class = max(raw_dist, key=raw_dist.get)
            top_prob = raw_dist[top_class]

            # Uncertainty handling
            if top_prob < self.uncertain_threshold:
                final_class = "uncertain"
                confidence = round(1.0 - top_prob, 4)
                class_probabilities = {**raw_dist, "uncertain": round(1.0 - top_prob, 4)}
            else:
                final_class = top_class
                confidence = round(top_prob, 4)
                class_probabilities = {**raw_dist, "uncertain": round(max(0.0, 1.0 - top_prob), 4)}

            # Feature attribution explanation
            explanation = self._explain_prediction(X.iloc[i], final_class)

            results.append({
                "predicted_class": final_class,
                "confidence_score": confidence,
                "stage1_class": max(
                    {"industrial": p_ind, "forest_or_natural_fire": p_forest, "agricultural_burning": p_agri, "mining_or_other": p_mining},
                    key=lambda k: {"industrial": p_ind, "forest_or_natural_fire": p_forest, "agricultural_burning": p_agri, "mining_or_other": p_mining}[k]
                ),
                "stage2_class": s2_class_pred,
                "class_probabilities": class_probabilities,
                "feature_importances": self.get_feature_importances(),
                "explanation": explanation,
            })

        return results

    def predict(self, X: pd.DataFrame) -> List[str]:
        """Return list of predicted top class strings."""
        details = self.predict_detailed(X)
        return [d["predicted_class"] for d in details]

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Return probability matrix for all 6 FIRE_CLASSES."""
        details = self.predict_detailed(X)
        matrix = []
        for d in details:
            row = [d["class_probabilities"].get(cls_name, 0.0) for cls_name in self.final_classes]
            total = sum(row) or 1.0
            matrix.append([v / total for v in row])
        return np.array(matrix, dtype=float)

    def get_feature_importances(self) -> Dict[str, float]:
        """Extract normalised feature importance attribution from Stage 1 model."""
        estimator = self.stage1_model
        if hasattr(estimator, "estimator_"):  # unwrap CalibratedClassifierCV
            estimator = estimator.estimator_
        elif hasattr(estimator, "calibrated_classifiers_") and estimator.calibrated_classifiers_:
            estimator = estimator.calibrated_classifiers_[0].estimator

        if hasattr(estimator, "feature_importances_"):
            imp = estimator.feature_importances_
            total = np.sum(imp) or 1.0
            return {
                feat: round(float(val / total), 4)
                for feat, val in zip(self.features, imp)
            }
        return {f: round(1.0 / len(self.features), 4) for f in self.features}

    def _explain_prediction(self, sample: pd.Series, predicted_class: str) -> Dict[str, Any]:
        """Generate human-interpretable evidence bullets based on top features."""
        evidence = []
        dist_fac = float(sample.get("dist_nearest_facility", 999.0))
        frp = float(sample.get("frp", 0.0))
        p_score = float(sample.get("persistence_score", 0.0))
        lc = int(sample.get("land_cover_class", 50))
        ndvi = float(sample.get("ndvi_value", 0.35))
        d_nbr = float(sample.get("delta_nbr", 0.0))

        if dist_fac < 0.3:
            evidence.append(f"Proximity to industrial facility: {dist_fac*1000:.0f}m")
        if p_score >= 3:
            evidence.append(f"High thermal recurrence score ({p_score:.0f} detections in 7d)")
        if frp > 100:
            evidence.append(f"Elevated Fire Radiative Power: {frp:.1f} MW")
        if d_nbr > 0.20:
            evidence.append(f"Significant Sentinel-2 burn index drop (ΔNBR: {d_nbr:.2f})")
        if lc == 10:
            evidence.append("ESA WorldCover: Tree cover / Forest zone")
        elif lc == 40:
            evidence.append("ESA WorldCover: Cropland / Agricultural zone")
        elif lc == 60:
            evidence.append("ESA WorldCover: Bare ground / Mining area")

        return {
            "top_factors": evidence[:4],
            "primary_driver": evidence[0] if evidence else "Spectral and proximity signature",
        }

    def _instantiate_base_model(self, algorithm: str, n_classes: int) -> Any:
        """Instantiate underlying estimator matching algorithm selection."""
        if algorithm == "xgboost" and XGB_AVAILABLE:
            params = DEFAULT_XGBOOST_PARAMS.copy()
            params["objective"] = "multi:softprob" if n_classes > 2 else "binary:logistic"
            params["num_class"] = n_classes if n_classes > 2 else None
            return xgb.XGBClassifier(**{k: v for k, v in params.items() if v is not None})
        elif algorithm == "hist_gradient_boosting":
            return HistGradientBoostingClassifier(**DEFAULT_HGB_PARAMS)
        elif algorithm == "logistic_regression":
            return LogisticRegression(**DEFAULT_LR_PARAMS)
        else:  # default random_forest
            return RandomForestClassifier(**DEFAULT_RF_PARAMS)

    def _prepare_matrix(self, X: pd.DataFrame, is_training: bool = False) -> np.ndarray:
        """Ensure all required feature columns exist, impute missing values, and format float32."""
        df = X.copy()
        for col in self.features:
            if col not in df.columns:
                df[col] = 0.0
        df = df[self.features].fillna(0.0)

        if self.algorithm == "logistic_regression":
            if is_training:
                self.scaler = StandardScaler()
                return self.scaler.fit_transform(df.values).astype(np.float32)
            elif self.scaler is not None:
                return self.scaler.transform(df.values).astype(np.float32)

        return df.values.astype(np.float32)
