"""Tests for Hotspots API endpoints."""

from __future__ import annotations

import datetime
import uuid
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.hotspot import Hotspot


def test_list_hotspots_empty(client: TestClient):
    response = client.get("/api/v1/hotspots")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["data"] == []
    assert data["meta"]["total"] == 0


def test_list_hotspots_with_data(client: TestClient, db_session: Session):
    h_id = uuid.uuid4()
    # WKB hex representation of POINT(69.87 22.47) with SRID 4326
    sample_geom = "0101000020E610000062105839B4F7514085EB51B81E783640"
    hotspot = Hotspot(
        id=h_id,
        latitude=22.47,
        longitude=69.87,
        geom=sample_geom,
        brightness=350.0,
        frp=120.0,
        confidence=90.0,
        satellite="SNPP",
        instrument="VIIRS",
        acq_date=datetime.date(2024, 9, 10),
        acq_time=datetime.time(12, 30),
        daynight="N",
        source="FIRMS",
    )
    db_session.add(hotspot)
    db_session.commit()

    response = client.get("/api/v1/hotspots")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["data"]) == 1
    assert data["data"][0]["latitude"] == 22.47
    assert data["data"][0]["longitude"] == 69.87


def test_get_single_hotspot_not_found(client: TestClient):
    random_id = uuid.uuid4()
    response = client.get(f"/api/v1/hotspots/{random_id}")
    assert response.status_code == 404


def test_get_single_hotspot_success(client: TestClient, db_session: Session):
    h_id = uuid.uuid4()
    sample_geom = "0101000020E610000062105839B4F7514085EB51B81E783640"
    hotspot = Hotspot(
        id=h_id,
        latitude=22.47,
        longitude=69.87,
        geom=sample_geom,
        brightness=380.0,
        frp=150.0,
        confidence=95.0,
        satellite="SNPP",
        instrument="VIIRS",
        acq_date=datetime.date(2024, 9, 10),
        acq_time=datetime.time(14, 0),
        daynight="N",
        source="FIRMS",
    )
    db_session.add(hotspot)
    db_session.commit()

    response = client.get(f"/api/v1/hotspots/{h_id}")
    assert response.status_code == 200
    data = response.json()
    # Detail endpoint returns HotspotDetailRead directly (no status/data wrapper)
    assert data["id"] == str(h_id)
    assert data["latitude"] == 22.47
