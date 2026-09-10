"""AgniNetra AI — Machine Learning Classifier.

Wraps XGBoost / scikit-learn multi-class fire classifier with probability outputs,
feature importance extraction, and serialization support.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.ensemble import RandomForestClassifier

from ml.config import DEFAULT_XGBOOST_PARAMS, FEATURE_COLUMNS, FIRE_CLASSES

logger = logging.getLogger(__name__)

# Try to import XGBoost if available, otherwise fallback to RandomForestClassifier
try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False
    logger.warning("XGBoost not installed, falling back to RandomForestClassifier.")


class ThermalFireClassifier(BaseEstimator, ClassifierMixin):
    """Multi-class thermal anomaly classifier for AgniNetra AI."""

    def __init__(
        self,
        features: Optional[List[str]] = None,
        classes: Optional[List[str]] = None,
        use_xgboost: bool = True,
        hyperparameters: Optional[Dict[str, Any]] = None,
    ):
        self.features = features or FEATURE_COLUMNS
        self.classes = classes or FIRE_CLASSES
        self.use_xgboost = use_xgboost and XGB_AVAILABLE
        self.hyperparameters = hyperparameters or (DEFAULT_XGBOOST_PARAMS if self.use_xgboost else {})
        self.model: Any = None
        self._class_to_idx = {c: i for i, c in enumerate(self.classes)}
        self._idx_to_class = {i: c for i, c in enumerate(self.classes)}

    def fit(self, X: pd.DataFrame, y: pd.Series | np.ndarray) -> ThermalFireClassifier:
        """Fit classifier on training feature matrix and target labels."""
        X_mat = self._prepare_features(X)
        y_vec = self._encode_labels(y)

        if self.use_xgboost:
            params = self.hyperparameters.copy()
            params["objective"] = "multi:softprob"
            params["num_class"] = len(self.classes)
            self.model = xgb.XGBClassifier(**params)
        else:
            self.model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=42,
            )

        self.model.fit(X_mat, y_vec)
        return self

    def predict(self, X: pd.DataFrame) -> List[str]:
        """Predict top class label string for each sample."""
        probas = self.predict_proba(X)
        pred_indices = np.argmax(probas, axis=1)
        return [self._idx_to_class[idx] for idx in pred_indices]

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Predict class probability distribution matrix [N, num_classes]."""
        if self.model is None:
            raise RuntimeError("Model has not been fitted yet. Call fit() first.")
        X_mat = self._prepare_features(X)
        return self.model.predict_proba(X_mat)

    def predict_detailed(self, X: pd.DataFrame) -> List[Dict[str, Any]]:
        """Return rich prediction results including top class, confidence, and class probabilities."""
        probas = self.predict_proba(X)
        results = []
        for i, row_proba in enumerate(probas):
            top_idx = int(np.argmax(row_proba))
            top_class = self._idx_to_class[top_idx]
            confidence = float(row_proba[top_idx])
            class_dict = {
                self._idx_to_class[j]: float(prob)
                for j, prob in enumerate(row_proba)
            }
            results.append({
                "predicted_class": top_class,
                "confidence_score": round(confidence, 4),
                "class_probabilities": class_dict,
            })
        return results

    def get_feature_importances(self) -> Dict[str, float]:
        """Extract normalised feature importances."""
        if self.model is None:
            raise RuntimeError("Model has not been fitted yet.")
        if hasattr(self.model, "feature_importances_"):
            importances = self.model.feature_importances_
            total = np.sum(importances) or 1.0
            return {
                feat: round(float(imp / total), 4)
                for feat, imp in zip(self.features, importances)
            }
        return {}

    def _prepare_features(self, X: pd.DataFrame) -> np.ndarray:
        """Validate and impute missing values for model input."""
        df = X.copy()
        for col in self.features:
            if col not in df.columns:
                df[col] = 0.0
        df = df[self.features].fillna(0.0)
        return df.values.astype(np.float32)

    def _encode_labels(self, y: pd.Series | np.ndarray) -> np.ndarray:
        """Encode string labels to integers."""
        if isinstance(y, pd.Series):
            y = y.values
        if y.dtype == object or isinstance(y[0], str):
            return np.array([self._class_to_idx.get(lbl, 5) for lbl in y], dtype=int)
        return np.asarray(y, dtype=int)
