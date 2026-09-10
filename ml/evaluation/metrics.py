"""AgniNetra AI — Machine Learning Evaluation Metrics.

Computes multi-class classification metrics: Accuracy, Precision, Recall, F1 (macro/weighted),
and confusion matrices.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

from ml.config import FIRE_CLASSES


def evaluate_classification(
    y_true: pd.Series | np.ndarray | List[str],
    y_pred: pd.Series | np.ndarray | List[str],
    y_prob: Optional[np.ndarray] = None,
    classes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Calculate standard multi-class evaluation metrics."""
    classes = classes or FIRE_CLASSES

    # Ensure array formats
    y_t = np.asarray(y_true)
    y_p = np.asarray(y_pred)

    acc = float(accuracy_score(y_t, y_p))
    prec_macro = float(precision_score(y_t, y_p, labels=classes, average="macro", zero_division=0))
    rec_macro = float(recall_score(y_t, y_p, labels=classes, average="macro", zero_division=0))
    f1_macro = float(f1_score(y_t, y_p, labels=classes, average="macro", zero_division=0))
    f1_weighted = float(f1_score(y_t, y_p, labels=classes, average="weighted", zero_division=0))

    cm = confusion_matrix(y_t, y_p, labels=classes)
    report = classification_report(y_t, y_p, labels=classes, output_dict=True, zero_division=0)

    results = {
        "accuracy": round(acc, 4),
        "macro_precision": round(prec_macro, 4),
        "macro_recall": round(rec_macro, 4),
        "macro_f1": round(f1_macro, 4),
        "weighted_f1": round(f1_weighted, 4),
        "confusion_matrix": cm.tolist(),
        "per_class_metrics": {
            cls_name: {
                "precision": round(float(report[cls_name]["precision"]), 4),
                "recall": round(float(report[cls_name]["recall"]), 4),
                "f1": round(float(report[cls_name]["f1-score"]), 4),
                "support": int(report[cls_name]["support"]),
            }
            for cls_name in classes
            if cls_name in report
        },
    }

    return results
