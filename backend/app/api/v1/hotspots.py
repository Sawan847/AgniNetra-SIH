"""Hotspot API endpoints with spatial filtering, pagination, and GeoJSON export."""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.hotspot import Hotspot
from app.models.prediction import Prediction
from app.schemas.hotspot import (
    GeoJSONGeometryPoint,
    HotspotDetailRead,
    HotspotGeoJSONFeature,
    HotspotGeoJSONFeatureCollection,
    HotspotListResponse,
    HotspotRead,
)

router = APIRouter()


@router.get(
    "/hotspots",
    response_model=None,
    summary="Query thermal hotspots with spatial, temporal, and classification filters",
)
def list_hotspots(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=500, description="Items per page"),
    min_frp: Optional[float] = Query(None, ge=0.0, description="Minimum Fire Radiative Power (MW)"),
    satellite: Optional[str] = Query(None, description="Filter by satellite (e.g. SNPP, NOAA-20, NOAA-21)"),
    start_date: Optional[datetime.date] = Query(None, description="Start acquisition date (YYYY-MM-DD)"),
    end_date: Optional[datetime.date] = Query(None, description="End acquisition date (YYYY-MM-DD)"),
    fire_class: Optional[str] = Query(None, description="Filter by predicted fire class"),
    bbox: Optional[str] = Query(None, description="Bounding box filter: min_lon,min_lat,max_lon,max_lat"),
    format: str = Query("json", description="Output format: 'json' or 'geojson'"),
    db: Session = Depends(get_db),
):
    """Retrieve paginated thermal anomalies with rich filters and GeoJSON support."""
    query = db.query(Hotspot)

    if min_frp is not None:
        query = query.filter(Hotspot.frp >= min_frp)
    if satellite:
        query = query.filter(Hotspot.satellite.ilike(f"%{satellite}%"))
    if start_date:
        query = query.filter(Hotspot.acq_date >= start_date)
    if end_date:
        query = query.filter(Hotspot.acq_date <= end_date)

    # Bounding box filter
    if bbox:
        try:
            parts = [float(p.strip()) for p in bbox.split(",")]
            if len(parts) == 4:
                min_lon, min_lat, max_lon, max_lat = parts
                query = query.filter(
                    Hotspot.latitude >= min_lat,
                    Hotspot.latitude <= max_lat,
                    Hotspot.longitude >= min_lon,
                    Hotspot.longitude <= max_lon,
                )
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid bbox format. Use: min_lon,min_lat,max_lon,max_lat")

    # Filter by predicted class via join
    if fire_class:
        query = query.join(Prediction, Hotspot.id == Prediction.hotspot_id).filter(
            Prediction.predicted_class == fire_class
        )

    total = query.count()
    rows = (
        query.order_by(desc(Hotspot.acq_date), desc(Hotspot.ingested_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    # Enrich with latest prediction class if available
    items = []
    for r in rows:
        pred_class = None
        conf = None
        if r.predictions:
            latest_pred = r.predictions[-1]
            pred_class = latest_pred.predicted_class
            conf = latest_pred.confidence_score

        item_dict = {
            "id": r.id,
            "event_id": r.event_id,
            "latitude": r.latitude,
            "longitude": r.longitude,
            "brightness": r.brightness,
            "bright_ti4": r.bright_ti4,
            "bright_ti5": r.bright_ti5,
            "frp": r.frp,
            "confidence": r.confidence,
            "satellite": r.satellite,
            "instrument": r.instrument,
            "acq_date": r.acq_date,
            "acq_time": r.acq_time,
            "daynight": r.daynight,
            "source": r.source,
            "ingested_at": r.ingested_at,
            "predicted_class": pred_class,
            "confidence_score": conf,
        }
        items.append(item_dict)

    if format.lower() == "geojson":
        features = [
            HotspotGeoJSONFeature(
                id=str(item["id"]),
                geometry=GeoJSONGeometryPoint(coordinates=[item["longitude"], item["latitude"]]),
                properties={k: v for k, v in item.items() if k not in ("latitude", "longitude")},
            )
            for item in items
        ]
        return HotspotGeoJSONFeatureCollection(
            features=features,
            meta={"total": total, "page": page, "per_page": per_page},
        )

    return HotspotListResponse(
        status="success",
        data=[HotspotRead.model_validate(item) for item in items],
        meta={"total": total, "page": page, "per_page": per_page},
    )


@router.get(
    "/hotspots/{hotspot_id}",
    response_model=HotspotDetailRead,
    summary="Get single hotspot by UUID with features, predictions, and alerts",
)
def get_hotspot(hotspot_id: uuid.UUID, db: Session = Depends(get_db)):
    """Retrieve full details of a specific thermal hotspot."""
    row = db.query(Hotspot).filter(Hotspot.id == hotspot_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Hotspot not found")

    pred_class = row.predictions[-1].predicted_class if row.predictions else None
    conf = row.predictions[-1].confidence_score if row.predictions else None

    # Format features
    features_dict = None
    if row.features:
        feat = row.features[-1]
        features_dict = {
            c.name: getattr(feat, c.name)
            for c in feat.__table__.columns
            if c.name not in ("id", "hotspot_id")
        }

    # Format predictions
    preds_list = [
        {
            "id": str(p.id),
            "predicted_class": p.predicted_class,
            "confidence_score": p.confidence_score,
            "class_probabilities": p.class_probabilities,
            "feature_importances": p.feature_importances,
            "explanation": p.explanation,
            "predicted_at": p.predicted_at.isoformat() if p.predicted_at else None,
        }
        for p in row.predictions
    ]

    # Format alerts
    alerts_list = [
        {
            "id": str(a.id),
            "severity": a.severity,
            "alert_type": a.alert_type,
            "status": a.status,
            "description": a.description,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in row.alerts
    ]

    return HotspotDetailRead(
        id=row.id,
        event_id=row.event_id,
        latitude=row.latitude,
        longitude=row.longitude,
        brightness=row.brightness,
        bright_ti4=row.bright_ti4,
        bright_ti5=row.bright_ti5,
        frp=row.frp,
        confidence=row.confidence,
        satellite=row.satellite,
        instrument=row.instrument,
        acq_date=row.acq_date,
        acq_time=row.acq_time,
        daynight=row.daynight,
        source=row.source,
        ingested_at=row.ingested_at,
        predicted_class=pred_class,
        confidence_score=conf,
        raw_data=row.raw_data,
        features=features_dict,
        predictions=preds_list,
        alerts=alerts_list,
    )
