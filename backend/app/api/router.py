"""Central API router that mounts all versioned sub-routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.hotspots import router as hotspots_router
from app.api.v1.facilities import router as facilities_router
from app.api.v1.predictions import router as predictions_router
from app.api.v1.alerts import router as alerts_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.model_metrics import router as model_metrics_router
from app.api.v1.system import router as system_router
from app.api.v1.ingestion import router as ingestion_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health_router, tags=["health"])
api_router.include_router(hotspots_router, tags=["hotspots"])
api_router.include_router(facilities_router, tags=["facilities"])
api_router.include_router(predictions_router, tags=["predictions"])
api_router.include_router(alerts_router, tags=["alerts"])
api_router.include_router(analytics_router, tags=["analytics"])
api_router.include_router(feedback_router, tags=["feedback"])
api_router.include_router(model_metrics_router, tags=["model"])
api_router.include_router(system_router, tags=["system"])
api_router.include_router(ingestion_router, tags=["ingestion"])
