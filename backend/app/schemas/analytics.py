"""Pydantic schemas for Analytics and Intelligence metrics."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class AnalyticsSummaryResponse(BaseModel):
    status: str = "success"
    total_hotspots: int
    total_facilities: int
    total_alerts: int
    active_alerts: int
    classification_distribution: Dict[str, int]
    severity_distribution: Dict[str, int]
    avg_frp: float
    max_frp: float
    satellite_sensor_distribution: Dict[str, int]
    recent_trend_7d: List[Dict[str, Any]]
