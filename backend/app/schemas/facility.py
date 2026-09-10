"""Pydantic schemas for Industrial Facility resources."""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class FacilityBase(BaseModel):
    name: Optional[str] = None
    facility_type: Optional[str] = Field(None, description="refinery, power_plant, industrial, mining")
    osm_id: Optional[str] = None
    source: Optional[str] = "OSM"


class FacilityRead(FacilityBase):
    id: uuid.UUID
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class FacilityListResponse(BaseModel):
    status: str = "success"
    data: List[FacilityRead]
    meta: Dict[str, Any]


class FacilityGeoJSONFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: str
    geometry: Dict[str, Any]
    properties: Dict[str, Any]


class FacilityGeoJSONFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: List[FacilityGeoJSONFeature]
    meta: Optional[Dict[str, Any]] = None
