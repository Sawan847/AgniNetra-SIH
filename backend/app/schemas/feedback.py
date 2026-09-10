"""Pydantic schemas for Analyst Feedback and Human-in-the-Loop Verification."""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class FeedbackCreate(BaseModel):
    hotspot_id: Optional[uuid.UUID] = None
    prediction_id: Optional[uuid.UUID] = None
    suggested_class: Optional[str] = None
    verified_class: str = Field(
        ...,
        description="accidental_industrial_fire, persistent_industrial_source, forest_or_natural_fire, agricultural_burning, mining_or_other, uncertain",
    )
    is_correct: bool = True
    reviewer_name: Optional[str] = "Analyst"
    label_source: str = Field("analyst_verified", description="analyst_verified, weak_rule, model_inference")
    evidence: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


class FeedbackRead(FeedbackCreate):
    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class FeedbackListResponse(BaseModel):
    status: str = "success"
    data: List[FeedbackRead]
    meta: Dict[str, Any]
