"""Predictions and ML Inference API endpoints."""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Dict, List, Optional
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
from app.services.gee import SatelliteFeatureService
from ml.features.engineering import extract_full_feature_vector
from ml.training.train import load_classifier_pipeline

router = APIRouter()

# Global cached instances
satellite_service = SatelliteFeatureService()
classifier_pipeline = None


def get_classifier():
    """Lazy loader for the two-stage classifier pipeline."""
    global classifier_pipeline
    if classifier_pipeline is None:
        classifier_pipeline = load_classifier_pipeline()
    return classifier_pipeline


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

    # 1. Fetch nearby facilities
    db_facilities = db.query(IndustrialFacility).limit(200).all()
    facility_dicts = []
    for f in db_facilities:
        loc_str = str(f.location or "")
        f_lat = None
        f_lon = None
        if "POINT(" in loc_str.upper():
            try:
                coords = loc_str.upper().split("POINT(")[1].split(")")[0].strip().split()
                f_lon = float(coords[0])
                f_lat = float(coords[1])
            except Exception:
                pass
        facility_dicts.append({
            "id": f.id,
            "name": f.name,
            "facility_type": f.facility_type,
            "latitude": f_lat or hotspot.latitude + 0.5,
            "longitude": f_lon or hotspot.longitude + 0.5,
        })

    # 2. Fetch historical hotspots for persistence & baselines
    hist_records = (
        db.query(Hotspot)
        .filter(Hotspot.id != hotspot.id)
        .filter(Hotspot.latitude.between(hotspot.latitude - 0.2, hotspot.latitude + 0.2))
        .filter(Hotspot.longitude.between(hotspot.longitude - 0.2, hotspot.longitude + 0.2))
        .limit(100)
        .all()
    )
    hist_dicts = [
        {"latitude": h.latitude, "longitude": h.longitude, "acq_date": h.acq_date, "frp": h.frp}
        for h in hist_records
    ]

    # 3. Fetch satellite spectral indices from GEE / Sentinel-2 service
    spectral = satellite_service.extract_spectral_features(
        lat=hotspot.latitude,
        lon=hotspot.longitude,
        acq_date=hotspot.acq_date or datetime.date.today(),
    )

    # 4. Extract complete 37-dimensional feature vector
    hotspot_dict = {
        "latitude": hotspot.latitude,
        "longitude": hotspot.longitude,
        "brightness": hotspot.brightness,
        "bright_ti4": hotspot.bright_ti4,
        "bright_ti5": hotspot.bright_ti5,
        "frp": hotspot.frp,
        "confidence": hotspot.confidence,
        "satellite": hotspot.satellite,
        "acq_date": hotspot.acq_date,
        "daynight": hotspot.daynight,
    }
    feature_dict = extract_full_feature_vector(
        hotspot_record=hotspot_dict,
        historical_hotspots=hist_dicts,
        facilities=facility_dicts,
        spectral_data=spectral,
    )

    # 5. Persist HotspotFeature record
    existing_feat = db.query(HotspotFeature).filter(HotspotFeature.hotspot_id == hotspot.id).first()
    if existing_feat:
        for k, v in feature_dict.items():
            if hasattr(existing_feat, k):
                setattr(existing_feat, k, v)
        feature_obj = existing_feat
    else:
        feature_obj = HotspotFeature(
            id=uuid.uuid4(),
            hotspot_id=hotspot.id,
            dist_nearest_facility=feature_dict.get("dist_nearest_facility"),
            is_inside_facility=bool(feature_dict.get("is_inside_facility")),
            nearby_facility_count_1km=int(feature_dict.get("nearby_facility_count_1km", 0)),
            nearby_facility_count_5km=int(feature_dict.get("nearby_facility_count_5km", 0)),
            dist_nearest_forest=feature_dict.get("dist_nearest_forest"),
            dist_nearest_cropland=feature_dict.get("dist_nearest_cropland"),
            dist_nearest_mine=feature_dict.get("dist_nearest_mine"),
            dist_nearest_settlement=feature_dict.get("dist_nearest_settlement"),
            nearby_hotspot_count_24h=int(feature_dict.get("nearby_hotspot_count_24h", 0)),
            nearby_hotspot_count_7d=int(feature_dict.get("nearby_hotspot_count_7d", 0)),
            nearby_hotspot_count_30d=int(feature_dict.get("nearby_hotspot_count_30d", 0)),
            nearby_hotspot_count_90d=int(feature_dict.get("nearby_hotspot_count_90d", 0)),
            persistence_score=feature_dict.get("persistence_score"),
            persistence_score_30d=feature_dict.get("persistence_score_30d"),
            recurrence_rate=feature_dict.get("recurrence_rate"),
            historical_median_frp=feature_dict.get("historical_median_frp"),
            historical_max_frp=feature_dict.get("historical_max_frp"),
            frp_to_historical_ratio=feature_dict.get("frp_to_historical_ratio"),
            cluster_size=int(feature_dict.get("cluster_size", 1)),
            cluster_spread_km=feature_dict.get("cluster_spread_km"),
            cluster_direction_deg=feature_dict.get("cluster_direction_deg"),
            spatial_density_5km=feature_dict.get("spatial_density_5km"),
            land_cover_class=int(feature_dict.get("land_cover_class", 50)),
            ndvi_value=feature_dict.get("ndvi_value"),
            nbr_value=feature_dict.get("nbr_value"),
            ndmi_value=feature_dict.get("ndmi_value"),
            delta_nbr=feature_dict.get("delta_nbr"),
            cloud_cover_fraction=feature_dict.get("cloud_cover_fraction"),
            imagery_available=bool(feature_dict.get("imagery_available")),
            is_nighttime=bool(feature_dict.get("is_nighttime")),
            day_of_year=int(feature_dict.get("day_of_year", 1)),
        )
        db.add(feature_obj)

    # 6. Run Two-Stage Model Inference
    import pandas as pd
    df_features = pd.DataFrame([feature_dict])
    model = get_classifier()
    pred_details = model.predict_detailed(df_features)[0]

    # 7. Persist Prediction record
    pred_obj = Prediction(
        id=uuid.uuid4(),
        hotspot_id=hotspot.id,
        predicted_class=pred_details["predicted_class"],
        confidence_score=pred_details["confidence_score"],
        stage1_class=pred_details.get("stage1_class"),
        stage2_class=pred_details.get("stage2_class"),
        class_probabilities=pred_details["class_probabilities"],
        feature_importances=pred_details["feature_importances"],
        explanation=pred_details.get("explanation"),
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
            metadata_={"explanation": pred_details.get("explanation")},
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
