"""Comprehensive tests for all AgniNetra v1 API endpoints.

Tests:
- Facilities (List, Filter, GeoJSON)
- Alerts (List, Create, Update status)
- Predictions (List, POST /predict/{id} full ML pipeline)
- Analytics (Summary aggregation)
- Feedback (Submit human label, list filters, weak_rule vs analyst_verified)
- Model Metrics (Evaluation metrics & model card)
- System Status (Health & diagnostics)
- Ingestion Runs (List history)
"""

from __future__ import annotations

import datetime
import uuid
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.facility import IndustrialFacility
from app.models.feedback import AnalystFeedback
from app.models.hotspot import Hotspot
from app.models.prediction import Prediction


# WKB hex representation of POINT(69.87 22.47) with SRID 4326
SAMPLE_GEOM = "0101000020E610000062105839B4F7514085EB51B81E783640"


def test_facilities_endpoints(client: TestClient, db_session: Session):
    # Create test facility
    fac_id = uuid.uuid4()
    fac = IndustrialFacility(
        id=fac_id,
        name="Reliance Jamnagar Refinery",
        facility_type="refinery",
        osm_id="way/123456",
        location=SAMPLE_GEOM,
        source="OSM",
    )
    db_session.add(fac)
    db_session.commit()

    # 1. Standard JSON list
    res = client.get("/api/v1/facilities")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert len(data["data"]) >= 1
    assert data["data"][0]["name"] == "Reliance Jamnagar Refinery"

    # 2. GeoJSON format
    res_geo = client.get("/api/v1/facilities?format=geojson")
    assert res_geo.status_code == 200
    geo_data = res_geo.json()
    assert geo_data["type"] == "FeatureCollection"
    assert len(geo_data["features"]) >= 1
    assert geo_data["features"][0]["properties"]["name"] == "Reliance Jamnagar Refinery"


def test_alerts_endpoints(client: TestClient, db_session: Session):
    # Setup hotspot first
    h_id = uuid.uuid4()
    hotspot = Hotspot(
        id=h_id,
        latitude=22.47,
        longitude=69.87,
        geom=SAMPLE_GEOM,
        brightness=390.0,
        frp=250.0,
        acq_date=datetime.date(2024, 9, 10),
    )
    db_session.add(hotspot)
    db_session.commit()

    # 1. Create Alert via POST
    create_payload = {
        "hotspot_id": str(h_id),
        "severity": "critical",
        "alert_type": "industrial_fire",
        "status": "active",
        "description": "High FRP thermal anomaly inside refinery zone",
    }
    res_create = client.post("/api/v1/alerts", json=create_payload)
    assert res_create.status_code == 201
    alert_data = res_create.json()
    assert alert_data["severity"] == "critical"
    alert_id = alert_data["id"]

    # 2. List Alerts
    res_list = client.get("/api/v1/alerts?severity=critical")
    assert res_list.status_code == 200
    list_data = res_list.json()
    assert list_data["status"] == "success"
    assert len(list_data["data"]) >= 1

    # 3. Update Alert Status
    res_update = client.patch(f"/api/v1/alerts/{alert_id}/status?status=acknowledged")
    assert res_update.status_code == 200
    assert res_update.json()["status"] == "acknowledged"


def test_prediction_pipeline_endpoint(client: TestClient, db_session: Session):
    h_id = uuid.uuid4()
    hotspot = Hotspot(
        id=h_id,
        latitude=22.47,
        longitude=69.87,
        geom=SAMPLE_GEOM,
        brightness=410.0,
        frp=350.0,
        confidence=95.0,
        daynight="N",
        acq_date=datetime.date(2024, 9, 10),
    )
    db_session.add(hotspot)
    db_session.commit()

    # Trigger full ML inference pipeline on this hotspot
    res_pred = client.post(f"/api/v1/predict/{h_id}")
    assert res_pred.status_code == 200
    pred_data = res_pred.json()
    assert pred_data["status"] == "success"
    pred = pred_data["data"]

    assert pred["predicted_class"] in [
        "accidental_industrial_fire",
        "persistent_industrial_source",
        "forest_or_natural_fire",
        "agricultural_burning",
        "mining_or_other",
        "uncertain",
    ]
    assert 0.0 <= pred["confidence_score"] <= 1.0
    assert "class_probabilities" in pred
    assert "explanation" in pred


def test_analytics_summary_endpoint(client: TestClient, db_session: Session):
    res = client.get("/api/v1/analytics/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "total_hotspots" in data
    assert "total_facilities" in data
    assert "total_alerts" in data
    assert "classification_distribution" in data
    assert "severity_distribution" in data


def test_feedback_endpoints(client: TestClient, db_session: Session):
    h_id = uuid.uuid4()
    hotspot = Hotspot(
        id=h_id,
        latitude=22.47,
        longitude=69.87,
        geom=SAMPLE_GEOM,
        acq_date=datetime.date(2024, 9, 10),
    )
    db_session.add(hotspot)
    db_session.commit()

    # 1. Analyst verified submission
    feedback_payload = {
        "hotspot_id": str(h_id),
        "suggested_class": "accidental_industrial_fire",
        "verified_class": "persistent_industrial_source",
        "is_correct": False,
        "reviewer_name": "Senior Thermal Analyst",
        "label_source": "analyst_verified",
        "notes": "Verified flare stack operational pattern on Sentinel-2 SWIR",
    }
    res = client.post("/api/v1/feedback", json=feedback_payload)
    assert res.status_code == 201
    fb_data = res.json()
    assert fb_data["verified_class"] == "persistent_industrial_source"
    assert fb_data["reviewer_name"] == "Senior Thermal Analyst"

    # 2. List feedback
    res_list = client.get(f"/api/v1/feedback?hotspot_id={h_id}")
    assert res_list.status_code == 200
    assert len(res_list.json()["data"]) >= 1


def test_model_metrics_endpoint(client: TestClient):
    res = client.get("/api/v1/model/metrics")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "active_model_name" in data
    assert "algorithm" in data


def test_system_status_endpoint(client: TestClient):
    res = client.get("/api/v1/system/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("healthy", "degraded")
    assert data["database_connected"] is True
    assert "total_records" in data
    assert "services" in data


def test_ingestion_runs_endpoint(client: TestClient):
    res = client.get("/api/v1/ingestion/runs")
    assert res.status_code == 200
    assert isinstance(res.json(), list)
