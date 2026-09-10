"""Pydantic schemas for Ingestion endpoints."""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field


class FIRMSIngestRequest(BaseModel):
    bbox: Tuple[float, float, float, float] = Field(
        ...,
        description="Bounding box: (min_lon, min_lat, max_lon, max_lat)",
        example=[68.0, 6.0, 97.5, 37.5],  # India
    )
    start_date: datetime.date = Field(
        default_factory=datetime.date.today,
        description="Start acquisition date (YYYY-MM-DD)",
    )
    end_date: Optional[datetime.date] = Field(
        None,
        description="End acquisition date (YYYY-MM-DD). If omitted, defaults to start_date",
    )
    sources: Optional[List[str]] = Field(
        ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT"],
        description="List of FIRMS VIIRS satellite sensors to query",
    )


class IngestionRunRead(BaseModel):
    id: uuid.UUID
    source: str
    status: str
    records_fetched: int
    records_inserted: int
    records_skipped: int
    error_message: Optional[str] = None
    started_at: datetime.datetime
    completed_at: Optional[datetime.datetime] = None

    model_config = ConfigDict(from_attributes=True)


class FIRMSIngestResponse(BaseModel):
    status: str = "success"
    message: str
    run_id: uuid.UUID
    data: Optional[IngestionRunRead] = None
