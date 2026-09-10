"""Pydantic schemas for Machine Learning Predictions."""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class PredictionRead(BaseModel):
    id: uuid.UUID
    hotspot_id: uuid.UUID
    model_version_id: Optional[uuid.UUID] = None
    predicted_class: str
    confidence_score: Optional[float] = None
    stage1_class: Optional[str] = None
    stage1_probabilities: Optional[Dict[str, float]] = None
    stage2_class: Optional[str] = None
    stage2_probabilities: Optional[Dict[str, float]] = None
    class_probabilities: Optional[Dict[str, float]] = None
    feature_importances: Optional[Dict[str, float]] = None
    explanation: Optional[Dict[str, Any]] = None
    predicted_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class PredictionListResponse(BaseModel):
    status: str = "success"
    data: List[PredictionRead]
    meta: Dict[str, Any]


class PredictResponse(BaseModel):
    status: str = "success"
    data: PredictionRead
    alert_created: bool = False
    alert_id: Optional[uuid.UUID] = None
