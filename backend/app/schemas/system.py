"""Pydantic schemas for System Status and Model Metrics."""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class SystemStatusResponse(BaseModel):
    status: str = "healthy"
    version: str = "0.1.0"
    environment: str = "development"
    timestamp: datetime.datetime
    database_connected: bool
    gee_connected: bool
    firms_configured: bool
    total_records: Dict[str, int]
    services: List[Dict[str, Any]]


class ModelMetricsResponse(BaseModel):
    status: str = "success"
    active_model_name: str
    algorithm: str
    version: str
    evaluation_metrics: Dict[str, Any]
    feature_importances: Dict[str, float]
    model_card: Optional[Dict[str, Any]] = None
