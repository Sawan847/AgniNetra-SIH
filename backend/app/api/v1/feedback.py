"""Analyst Feedback endpoints — human-in-the-loop labelling and verification."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.feedback import AnalystFeedback
from app.schemas.feedback import FeedbackCreate, FeedbackListResponse, FeedbackRead

router = APIRouter()


@router.post("/feedback", response_model=FeedbackRead, status_code=201)
def create_feedback(
    body: FeedbackCreate,
    db: Session = Depends(get_db),
) -> AnalystFeedback:
    """Submit analyst feedback or label verification for a hotspot/prediction.

    Weak rules may set label_source='weak_rule' but must never use 'analyst_verified'
    unless a human analyst explicitly submits the label.
    """
    if body.label_source == "analyst_verified" and not body.reviewer_name:
        raise HTTPException(
            status_code=422,
            detail="reviewer_name is required when label_source is 'analyst_verified'.",
        )

    feedback = AnalystFeedback(
        id=uuid.uuid4(),
        hotspot_id=body.hotspot_id,
        prediction_id=body.prediction_id,
        suggested_class=body.suggested_class,
        verified_class=body.verified_class,
        is_correct=body.is_correct,
        reviewer_name=body.reviewer_name,
        label_source=body.label_source,
        evidence=body.evidence,
        notes=body.notes,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


@router.get("/feedback", response_model=FeedbackListResponse)
def list_feedback(
    hotspot_id: Optional[uuid.UUID] = Query(None),
    prediction_id: Optional[uuid.UUID] = Query(None),
    verified_class: Optional[str] = Query(None),
    label_source: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> FeedbackListResponse:
    """List analyst feedback entries with optional filters."""
    query = db.query(AnalystFeedback)

    if hotspot_id:
        query = query.filter(AnalystFeedback.hotspot_id == hotspot_id)
    if prediction_id:
        query = query.filter(AnalystFeedback.prediction_id == prediction_id)
    if verified_class:
        query = query.filter(AnalystFeedback.verified_class == verified_class)
    if label_source:
        query = query.filter(AnalystFeedback.label_source == label_source)

    total = query.count()
    items = query.order_by(AnalystFeedback.created_at.desc()).offset(offset).limit(limit).all()

    return FeedbackListResponse(
        data=[FeedbackRead.model_validate(item) for item in items],
        meta={"total": total, "limit": limit, "offset": offset},
    )
