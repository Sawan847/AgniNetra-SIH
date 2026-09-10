"""Ingestion endpoints — trigger and monitor FIRMS data ingestion runs."""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.ingestion import IngestionRun
from app.schemas.ingestion import FIRMSIngestRequest, FIRMSIngestResponse, IngestionRunRead
from app.services.ingestion import IngestionService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/ingestion/firms", response_model=FIRMSIngestResponse, status_code=202)
def trigger_firms_ingestion(
    body: FIRMSIngestRequest,
    db: Session = Depends(get_db),
) -> FIRMSIngestResponse:
    """Trigger a FIRMS data ingestion run for the specified bounding box and date range.

    The MAP_KEY is never logged, returned, or exposed in any response.
    """
    service = IngestionService(db)

    try:
        run = service.run_firms_ingestion(
            bbox=body.bbox,
            start_date=body.start_date,
            end_date=body.end_date,
            sources=body.sources,
        )
    except Exception as exc:
        logger.error("FIRMS ingestion failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}")

    status_msg = (
        f"Ingestion {run.status}: {run.records_inserted} inserted, "
        f"{run.records_skipped} skipped out of {run.records_fetched} fetched."
    )

    return FIRMSIngestResponse(
        status=run.status,
        message=status_msg,
        run_id=run.id,
        data=IngestionRunRead.model_validate(run),
    )


@router.get("/ingestion/runs", response_model=List[IngestionRunRead])
def list_ingestion_runs(
    status: Optional[str] = Query(None, description="Filter by status: running, completed, failed"),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> List[IngestionRunRead]:
    """List recent ingestion runs with optional status filter."""
    query = db.query(IngestionRun)

    if status:
        query = query.filter(IngestionRun.status == status)

    runs = query.order_by(IngestionRun.started_at.desc()).offset(offset).limit(limit).all()
    return [IngestionRunRead.model_validate(r) for r in runs]
