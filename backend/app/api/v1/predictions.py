"""Predictions and ML Inference API endpoints."""

from __future__ import annotations

import datetime
import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.alert import Alert
from app.models.facility import IndustrialFacility
from app.models.hotspot import Hotspot
from app.models.prediction import HotspotFeature, Prediction
from app.schemas.prediction import (
    PredictionListResponse,
    PredictionRead,
    PredictResponse,
)
from app.services.classifier import (
    CONTEXT_RADIUS_DEG,
    CONTEXT_WINDOW_DAYS,
    classifier_service,
)
from app.services.gee import SatelliteFeatureService

logger = logging.getLogger(__name__)

router = APIRouter()

satellite_service = SatelliteFeatureService()

_POINT_RE = re.compile(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)", re.IGNORECASE)


def _parse_point(location: Any) -> Tuple[Optional[float], Optional[float]]:
    """Extract (lat, lon) from a WKT/EWKT POINT, or (None, None) if unparseable.

    Returning None is deliberate: the caller must skip the facility rather than
    substitute a guessed coordinate.
    """
    if location is None:
        return None, None
    match = _POINT_RE.search(str(location))
    if not match:
        return None, None
    try:
        lon, lat = float(match.group(1)), float(match.group(2))
    except (TypeError, ValueError):
        return None, None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None, None
    return lat, lon


def _facility_category(facility_type: Any) -> str:
    """Map a stored facility type onto the categories the features use."""
    text = str(facility_type or "").lower()
    if any(k in text for k in ("quarry", "mine", "mining", "colliery")):
        return "mine"
    if any(k in text for k in ("landfill", "waste", "dump")):
        return "landfill"
    return "industrial"


def _hotspot_to_record(h: Hotspot) -> Dict[str, Any]:
    """Convert a Hotspot row into the raw detection shape the feature pipeline takes."""
    return {
        "latitude": h.latitude,
        "longitude": h.longitude,
        "bright_ti4": h.bright_ti4 if h.bright_ti4 is not None else h.brightness,
        "bright_ti5": h.bright_ti5,
        "frp": h.frp,
        "confidence": h.confidence,
        "acq_date": h.acq_date.isoformat() if h.acq_date else None,
        "daynight": h.daynight or "D",
        "satellite": h.satellite,
        "land_cover_class": getattr(h, "land_cover_class", None) or 0,
    }


@router.get(
    "/predictions",
    response_model=PredictionListResponse,
    summary="Query historical model predictions",
)
def list_predictions(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    predicted_class: Optional[str] = Query(None, description="Filter by class"),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
):
    """Retrieve paginated model prediction logs."""
    query = db.query(Prediction)
    if predicted_class:
        query = query.filter(Prediction.predicted_class == predicted_class)
    if min_confidence is not None:
        query = query.filter(Prediction.confidence_score >= min_confidence)

    total = query.count()
    rows = query.order_by(desc(Prediction.predicted_at)).offset((page - 1) * per_page).limit(per_page).all()

    return PredictionListResponse(
        status="success",
        data=[PredictionRead.model_validate(r) for r in rows],
        meta={"total": total, "page": page, "per_page": per_page},
    )


@router.post(
    "/predict/{hotspot_id}",
    response_model=PredictResponse,
    summary="Execute end-to-end feature extraction, two-stage classification, and alert triggers",
)
def run_prediction_for_hotspot(hotspot_id: uuid.UUID, db: Session = Depends(get_db)):
    """Run full intelligence pipeline for a specific hotspot record."""
    hotspot = db.query(Hotspot).filter(Hotspot.id == hotspot_id).first()
    if not hotspot:
        raise HTTPException(status_code=404, detail="Hotspot not found")

    # 1. Fetch nearby facilities.
    #
    # A facility whose geometry cannot be parsed is SKIPPED, not invented. This
    # previously fell back to `hotspot.latitude + 0.5`, placing a phantom facility
    # ~55 km away and feeding that made-up distance straight into the model.
    db_facilities = db.query(IndustrialFacility).limit(2000).all()
    facility_dicts = []
    skipped_facilities = 0
    for f in db_facilities:
        f_lat, f_lon = _parse_point(f.location)
        if f_lat is None or f_lon is None:
            skipped_facilities += 1
            continue
        facility_dicts.append({
            "id": f.id,
            "name": f.name,
            "category": _facility_category(f.facility_type),
            "latitude": f_lat,
            "longitude": f_lon,
        })
    if skipped_facilities:
        logger.warning(
            "Skipped %d facilities with unparseable geometry", skipped_facilities
        )

    # 2. Fetch the detection's spatial-temporal neighbourhood.
    #
    # Persistence is meaningless without history: one night tells you nothing about
    # whether a source is permanent. The window must be wide enough to establish a
    # baseline and tight enough that unrelated sources do not pollute the cluster.
    target_date = hotspot.acq_date or datetime.date.today()
    window_start = target_date - datetime.timedelta(days=CONTEXT_WINDOW_DAYS)

    hist_records = (
        db.query(Hotspot)
        .filter(Hotspot.id != hotspot.id)
        .filter(Hotspot.latitude.between(
            hotspot.latitude - CONTEXT_RADIUS_DEG, hotspot.latitude + CONTEXT_RADIUS_DEG))
        .filter(Hotspot.longitude.between(
            hotspot.longitude - CONTEXT_RADIUS_DEG, hotspot.longitude + CONTEXT_RADIUS_DEG))
        .filter(Hotspot.acq_date >= window_start)
        .filter(Hotspot.acq_date <= target_date)
        .limit(5000)
        .all()
    )

    # 3. Score the detection in the context of its neighbourhood.
    #
    # The target detection is placed FIRST so its index is known, then its neighbours
    # follow. The classifier computes site clustering and persistence across the whole
    # batch and returns the target's result.
    detections = [_hotspot_to_record(hotspot)] + [_hotspot_to_record(h) for h in hist_records]

    try:
        scored = classifier_service.classify_detections(
            detections, facilities=facility_dicts, target_index=0
        )[0]
    except RuntimeError as exc:
        # No trained artifact. Fail with an actionable message rather than silently
        # training a model inside a request handler, which is what used to happen.
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    feature_dict = scored.get("features", {})

    # 4. Spectral indices are advisory only and are never imputed. When Earth Engine
    # is unconfigured this returns imagery_available=False and null values, and the
    # classifier simply runs without them.
    spectral = satellite_service.extract_spectral_features(
        lat=hotspot.latitude,
        lon=hotspot.longitude,
        acq_date=target_date,
    )

    # 5. Persist the engineered features.
    #
    # Column names on HotspotFeature predate the site-level pipeline, so the new
    # measured values are mapped onto the existing schema. Spectral columns are
    # written only when imagery was genuinely retrieved.
    imagery_ok = bool(spectral.get("imagery_available"))
    mapped = {
        "dist_nearest_facility": feature_dict.get("dist_industrial_km"),
        "is_inside_facility": bool(feature_dict.get("is_inside_industrial") or 0),
        "nearby_facility_count_5km": int(feature_dict.get("count_industrial_5km") or 0),
        "dist_nearest_mine": feature_dict.get("dist_mine_km"),
        "persistence_score": feature_dict.get("persistence_ratio"),
        "historical_median_frp": feature_dict.get("site_frp_median"),
        "frp_to_historical_ratio": feature_dict.get("frp_to_site_baseline"),
        "cluster_size": int(feature_dict.get("cluster_size") or 1),
        "cluster_spread_km": feature_dict.get("cluster_spread_km"),
        "land_cover_class": int(feature_dict.get("land_cover_class") or 0),
        "is_nighttime": bool(feature_dict.get("is_nighttime") or 0),
        "day_of_year": int(feature_dict.get("day_of_year") or 1),
        "ndvi_value": spectral.get("ndvi_value") if imagery_ok else None,
        "nbr_value": spectral.get("nbr_value") if imagery_ok else None,
        "ndmi_value": spectral.get("ndmi_value") if imagery_ok else None,
        "delta_nbr": spectral.get("delta_nbr") if imagery_ok else None,
        "cloud_cover_fraction": spectral.get("cloud_cover_fraction") if imagery_ok else None,
        "imagery_available": imagery_ok,
    }

    feature_obj = (
        db.query(HotspotFeature).filter(HotspotFeature.hotspot_id == hotspot.id).first()
    )
    if feature_obj is None:
        feature_obj = HotspotFeature(id=uuid.uuid4(), hotspot_id=hotspot.id)
        db.add(feature_obj)
    for key, val in mapped.items():
        if hasattr(feature_obj, key):
            setattr(feature_obj, key, val)

    # 6. Persist the prediction.
    #
    # predicted_class is "uncertain" when the model abstained; requires_human_review
    # carries that decision through to the operations queue rather than the model
    # guessing a class it is not confident about.
    probs = scored["class_probabilities"]
    evidence = scored["evidence"]

    pred_obj = Prediction(
        id=uuid.uuid4(),
        hotspot_id=hotspot.id,
        predicted_class=scored["predicted_class"],
        confidence_score=scored["confidence"],
        stage1_class=scored["predicted_class"],
        stage2_class=None,
        class_probabilities=probs,
        feature_importances={},
        explanation={
            "top_factors": evidence["factors"],
            "primary_driver": evidence["primary"],
            "requires_human_review": scored["requires_human_review"],
            "site_id": scored["site_id"],
            "persistence_ratio": scored["persistence_ratio"],
        },
        predicted_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db.add(pred_obj)
    db.flush()

    # 8. Automated Critical Incident Alert Triggering
    alert_created = False
    alert_id = None
    if (
        pred_obj.predicted_class == "accidental_industrial_fire"
        and (pred_obj.confidence_score or 0) >= 0.70
    ):
        alert_obj = Alert(
            id=uuid.uuid4(),
            hotspot_id=hotspot.id,
            prediction_id=pred_obj.id,
            severity="critical",
            alert_type="accidental_industrial_fire",
            status="active",
            description=(
                f"CRITICAL: Probable accidental industrial fire detected at ({hotspot.latitude:.4f}, {hotspot.longitude:.4f}) "
                f"with {pred_obj.confidence_score*100:.1f}% confidence. FRP: {hotspot.frp} MW."
            ),
            metadata_={
                "evidence": evidence["factors"],
                "primary_driver": evidence["primary"],
                "persistence_ratio": scored["persistence_ratio"],
            },
        )
        db.add(alert_obj)
        alert_created = True
        alert_id = alert_obj.id

    db.commit()
    db.refresh(pred_obj)

    return PredictResponse(
        status="success",
        data=PredictionRead.model_validate(pred_obj),
        alert_created=alert_created,
        alert_id=alert_id,
    )
