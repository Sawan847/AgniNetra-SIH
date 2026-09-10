"""System status endpoint — health diagnostics for all subsystems."""

from __future__ import annotations

import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.alert import Alert
from app.models.facility import IndustrialFacility
from app.models.hotspot import Hotspot
from app.models.ingestion import IngestionRun
from app.models.prediction import Prediction
from app.schemas.system import SystemStatusResponse

router = APIRouter()


@router.get("/system/status", response_model=SystemStatusResponse)
def get_system_status(
    db: Session = Depends(get_db),
) -> SystemStatusResponse:
    """Return comprehensive system health: database, FIRMS, GEE, and record counts."""

    # Database connectivity check
    db_connected = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_connected = False

    # FIRMS configuration check (never expose the key)
    firms_configured = bool(settings.effective_firms_map_key)

    # GEE configuration check
    gee_connected = bool(settings.ee_project_id and settings.ee_service_account)

    # Record counts
    total_records: Dict[str, int] = {}
    try:
        total_records["hotspots"] = db.query(func.count(Hotspot.id)).scalar() or 0
        total_records["facilities"] = db.query(func.count(IndustrialFacility.id)).scalar() or 0
        total_records["predictions"] = db.query(func.count(Prediction.id)).scalar() or 0
        total_records["alerts"] = db.query(func.count(Alert.id)).scalar() or 0
        total_records["ingestion_runs"] = db.query(func.count(IngestionRun.id)).scalar() or 0
    except Exception:
        pass

    # Build services list
    services: List[Dict[str, Any]] = [
        {
            "name": "database",
            "status": "healthy" if db_connected else "unreachable",
            "backend": settings.database_url.split("://")[0] if "://" in settings.database_url else "unknown",
        },
        {
            "name": "firms_api",
            "status": "configured" if firms_configured else "not_configured",
        },
        {
            "name": "google_earth_engine",
            "status": "configured" if gee_connected else "mock_fallback",
        },
    ]

    return SystemStatusResponse(
        status="healthy" if db_connected else "degraded",
        version="0.1.0",
        environment=settings.environment,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
        database_connected=db_connected,
        gee_connected=gee_connected,
        firms_configured=firms_configured,
        total_records=total_records,
        services=services,
    )
