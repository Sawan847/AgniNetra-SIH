"""Pydantic schemas for Hotspot resources with GeoJSON support."""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class HotspotBase(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    brightness: Optional[float] = None
    bright_ti4: Optional[float] = None
    bright_ti5: Optional[float] = None
    frp: Optional[float] = Field(None, description="Fire Radiative Power (MW)")
    confidence: Optional[float] = None
    satellite: Optional[str] = None
    instrument: Optional[str] = None
    acq_date: Optional[datetime.date] = None
    acq_time: Optional[datetime.time] = None
    daynight: Optional[str] = None
    source: Optional[str] = None


class HotspotRead(HotspotBase):
    id: uuid.UUID
    event_id: Optional[str] = None
    ingested_at: datetime.datetime
    predicted_class: Optional[str] = None
    confidence_score: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class HotspotDetailRead(HotspotRead):
    raw_data: Optional[Dict[str, Any]] = None
    features: Optional[Dict[str, Any]] = None
    predictions: Optional[List[Dict[str, Any]]] = None
    alerts: Optional[List[Dict[str, Any]]] = None


class HotspotListResponse(BaseModel):
    status: str = "success"
    data: List[HotspotRead]
    meta: Dict[str, Any]


class GeoJSONGeometryPoint(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: List[float]  # [longitude, latitude]


class HotspotGeoJSONFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: str
    geometry: GeoJSONGeometryPoint
    properties: Dict[str, Any]


class HotspotGeoJSONFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: List[HotspotGeoJSONFeature]
    meta: Optional[Dict[str, Any]] = None
