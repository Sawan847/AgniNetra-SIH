"""Analytics summary endpoint — aggregated platform statistics."""

from __future__ import annotations

import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.alert import Alert
from app.models.facility import IndustrialFacility
from app.models.hotspot import Hotspot
from app.models.prediction import Prediction
from app.schemas.analytics import AnalyticsSummaryResponse

router = APIRouter()


@router.get("/analytics/summary", response_model=AnalyticsSummaryResponse)
def get_analytics_summary(db: Session = Depends(get_db)) -> AnalyticsSummaryResponse:
    """Return aggregated platform analytics: counts, distributions, trends."""
    total_hotspots = db.query(func.count(Hotspot.id)).scalar() or 0
    total_facilities = db.query(func.count(IndustrialFacility.id)).scalar() or 0
    total_alerts = db.query(func.count(Alert.id)).scalar() or 0
    active_alerts = (
        db.query(func.count(Alert.id))
        .filter(Alert.status == "active")
        .scalar()
        or 0
    )

    # Classification distribution from predictions
    class_rows = (
        db.query(Prediction.predicted_class, func.count(Prediction.id))
        .group_by(Prediction.predicted_class)
        .all()
    )
    classification_distribution: Dict[str, int] = {row[0]: row[1] for row in class_rows}

    # Severity distribution from alerts
    sev_rows = (
        db.query(Alert.severity, func.count(Alert.id))
        .group_by(Alert.severity)
        .all()
    )
    severity_distribution: Dict[str, int] = {row[0]: row[1] for row in sev_rows}

    # FRP statistics
    avg_frp = db.query(func.avg(Hotspot.frp)).scalar()
    max_frp = db.query(func.max(Hotspot.frp)).scalar()

    # Satellite sensor distribution
    sat_rows = (
        db.query(Hotspot.satellite, func.count(Hotspot.id))
        .filter(Hotspot.satellite.isnot(None))
        .group_by(Hotspot.satellite)
        .all()
    )
    satellite_sensor_distribution: Dict[str, int] = {row[0]: row[1] for row in sat_rows}

    # 7-day trend: daily hotspot counts
    cutoff = datetime.date.today() - datetime.timedelta(days=7)
    trend_rows = (
        db.query(Hotspot.acq_date, func.count(Hotspot.id))
        .filter(Hotspot.acq_date >= cutoff)
        .group_by(Hotspot.acq_date)
        .order_by(Hotspot.acq_date)
        .all()
    )
    recent_trend_7d: List[Dict[str, Any]] = [
        {"date": str(row[0]), "count": row[1]} for row in trend_rows
    ]

    return AnalyticsSummaryResponse(
        total_hotspots=total_hotspots,
        total_facilities=total_facilities,
        total_alerts=total_alerts,
        active_alerts=active_alerts,
        classification_distribution=classification_distribution,
        severity_distribution=severity_distribution,
        avg_frp=round(float(avg_frp or 0.0), 2),
        max_frp=round(float(max_frp or 0.0), 2),
        satellite_sensor_distribution=satellite_sensor_distribution,
        recent_trend_7d=recent_trend_7d,
    )
