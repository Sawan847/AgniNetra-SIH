"""Health-check response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ServiceStatus(BaseModel):
    """Status of an individual service dependency."""

    name: str
    status: str  # "healthy" | "unhealthy"
    latency_ms: float | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Full health-check response."""

    status: str  # "healthy" | "degraded" | "unhealthy"
    version: str
    environment: str
    timestamp: datetime
    services: list[ServiceStatus]
