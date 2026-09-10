"""Health-check endpoints."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.health import HealthResponse, ServiceStatus

router = APIRouter()

APP_VERSION = "0.1.0"


@router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)) -> HealthResponse:
    """Return overall application health including database connectivity."""
    services: list[ServiceStatus] = []

    # Check database
    db_status = _check_database(db)
    services.append(db_status)

    overall = "healthy" if all(s.status == "healthy" for s in services) else "unhealthy"

    return HealthResponse(
        status=overall,
        version=APP_VERSION,
        environment="development",
        timestamp=datetime.now(timezone.utc),
        services=services,
    )


@router.get("/health/ready")
def readiness_check(db: Session = Depends(get_db)) -> dict:
    """Kubernetes-style readiness probe."""
    try:
        db.execute(text("SELECT 1"))
        return {"ready": True}
    except Exception:
        return {"ready": False}


def _check_database(db: Session) -> ServiceStatus:
    """Probe database connectivity and measure latency."""
    try:
        start = time.perf_counter()
        db.execute(text("SELECT 1"))
        latency = (time.perf_counter() - start) * 1000
        return ServiceStatus(name="postgresql", status="healthy", latency_ms=round(latency, 2))
    except Exception as exc:
        return ServiceStatus(name="postgresql", status="unhealthy", error=str(exc))
