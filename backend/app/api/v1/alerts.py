"""Incident Alerts API endpoints."""

from __future__ import annotations

import datetime
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.alert import Alert
from app.schemas.alert import AlertCreate, AlertListResponse, AlertRead, AlertUpdate

router = APIRouter()


@router.get(
    "/alerts",
    response_model=AlertListResponse,
    summary="List operational incident alerts with severity and status filters",
)
def list_alerts(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    status: Optional[str] = Query(None, description="active, acknowledged, resolved, false_positive"),
    severity: Optional[str] = Query(None, description="critical, high, medium, low"),
    db: Session = Depends(get_db),
):
    """Retrieve paginated active and historical alerts."""
    query = db.query(Alert)
    if status:
        query = query.filter(Alert.status == status)
    if severity:
        query = query.filter(Alert.severity == severity)

    total = query.count()
    rows = query.order_by(desc(Alert.created_at)).offset((page - 1) * per_page).limit(per_page).all()

    return AlertListResponse(
        status="success",
        data=[
            AlertRead(
                id=r.id,
                hotspot_id=r.hotspot_id,
                prediction_id=r.prediction_id,
                severity=r.severity,
                alert_type=r.alert_type,
                status=r.status,
                description=r.description,
                metadata=r.metadata_,
                created_at=r.created_at,
                resolved_at=r.resolved_at,
            )
            for r in rows
        ],
        meta={"total": total, "page": page, "per_page": per_page},
    )


@router.post(
    "/alerts",
    response_model=AlertRead,
    status_code=201,
    summary="Create a new manual or automated operational alert",
)
def create_alert(payload: AlertCreate, db: Session = Depends(get_db)):
    """Create a new incident alert."""
    alert_obj = Alert(
        id=uuid.uuid4(),
        hotspot_id=payload.hotspot_id,
        prediction_id=payload.prediction_id,
        severity=payload.severity,
        alert_type=payload.alert_type,
        status=payload.status or "active",
        description=payload.description,
        metadata_=payload.metadata,
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db.add(alert_obj)
    db.commit()
    db.refresh(alert_obj)

    return AlertRead(
        id=alert_obj.id,
        hotspot_id=alert_obj.hotspot_id,
        prediction_id=alert_obj.prediction_id,
        severity=alert_obj.severity,
        alert_type=alert_obj.alert_type,
        status=alert_obj.status,
        description=alert_obj.description,
        metadata=alert_obj.metadata_,
        created_at=alert_obj.created_at,
        resolved_at=alert_obj.resolved_at,
    )


@router.patch(
    "/alerts/{alert_id}",
    response_model=AlertRead,
    summary="Update alert status (e.g. acknowledge, resolve, mark false positive)",
)
def update_alert(alert_id: uuid.UUID, payload: AlertUpdate, db: Session = Depends(get_db)):
    """Update lifecycle status of an operational alert."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if payload.status:
        alert.status = payload.status
        if payload.status in ("resolved", "false_positive") and not alert.resolved_at:
            alert.resolved_at = datetime.datetime.now(datetime.timezone.utc)
    if payload.severity:
        alert.severity = payload.severity
    if payload.description:
        alert.description = payload.description
    if payload.resolved_at is not None:
        alert.resolved_at = payload.resolved_at

    db.commit()
    db.refresh(alert)

    return AlertRead(
        id=alert.id,
        hotspot_id=alert.hotspot_id,
        prediction_id=alert.prediction_id,
        severity=alert.severity,
        alert_type=alert.alert_type,
        status=alert.status,
        description=alert.description,
        metadata=alert.metadata_,
        created_at=alert.created_at,
        resolved_at=alert.resolved_at,
    )


@router.patch(
    "/alerts/{alert_id}/status",
    response_model=AlertRead,
    summary="Update alert status directly via query parameter or body",
)
def update_alert_status(
    alert_id: uuid.UUID,
    status: str = Query(..., description="active, acknowledged, resolved, false_positive"),
    db: Session = Depends(get_db),
):
    """Directly update status of an alert."""
    return update_alert(alert_id=alert_id, payload=AlertUpdate(status=status), db=db)

