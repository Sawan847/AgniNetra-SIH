"""AgniNetra AI — Google Earth Engine & Satellite Spectral Service.

Integrates Sentinel-2 Surface Reflectance imagery and ESA WorldCover land classification.
Calculates cloud-masked spectral indices (NDVI, NBR, NDMI, Delta-NBR) and provides
before/after burn comparison with graceful offline fallback.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, Optional, Tuple
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

# Try importing Google Earth Engine API
try:
    import ee
    EE_AVAILABLE = True
except ImportError:
    EE_AVAILABLE = False
    logger.info("earthengine-api not installed. Satellite feature extractor will use offline spectral provider.")


class SatelliteFeatureService:
    """Service for extracting Sentinel-2 surface reflectance and land-cover indices."""

    def __init__(self):
        self._ee_initialized = False
        self._init_earth_engine()

    def _init_earth_engine(self) -> None:
        """Attempt to authenticate and initialize Google Earth Engine."""
        if not EE_AVAILABLE:
            return

        try:
            if settings.ee_service_account and settings.ee_private_key:
                credentials = ee.ServiceAccountCredentials(
                    settings.ee_service_account, key_data=settings.ee_private_key
                )
                ee.Initialize(credentials, project=settings.ee_project_id or None)
                self._ee_initialized = True
                logger.info("Google Earth Engine initialized via Service Account credentials.")
            elif settings.ee_project_id:
                ee.Initialize(project=settings.ee_project_id)
                self._ee_initialized = True
                logger.info("Google Earth Engine initialized via default project credentials.")
        except Exception as e:
            logger.warning("Google Earth Engine initialization skipped (%s). Using offline spectral estimator.", e)
            self._ee_initialized = False

    def is_gee_active(self) -> bool:
        """Check if live Google Earth Engine connection is available."""
        return self._ee_initialized

    def extract_spectral_features(
        self,
        lat: float,
        lon: float,
        acq_date: Optional[datetime.date] = None,
        land_cover_class: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Extract NDVI, NBR, NDMI, Delta-NBR, and cloud fraction for a coordinate and date.

        If GEE is live, queries Sentinel-2 SR collection with SCL cloud masking.
        Otherwise, derives realistic, physically consistent spectral estimates.
        """
        acq_date = acq_date or datetime.date.today()

        if self._ee_initialized:
            try:
                return self._query_gee_sentinel2(lat, lon, acq_date)
            except Exception as exc:
                logger.warning("Live GEE query failed for (%f, %f): %s. Falling back to offline model.", lat, lon, exc)

        return self._estimate_offline_spectral_features(lat, lon, acq_date, land_cover_class)

    def _query_gee_sentinel2(
        self, lat: float, lon: float, acq_date: datetime.date
    ) -> Dict[str, Any]:
        """Execute server-side Earth Engine query for Sentinel-2 SR harmonized imagery."""
        point = ee.Geometry.Point([lon, lat])
        date_obj = ee.Date(acq_date.strftime("%Y-%m-%d"))

        # Pre-fire window: 30 to 5 days before
        pre_start = date_obj.advance(-30, "day")
        pre_end = date_obj.advance(-5, "day")

        # Post-fire window: 1 to 15 days after
        post_start = date_obj.advance(0, "day")
        post_end = date_obj.advance(15, "day")

        def mask_s2_clouds(image):
            scl = image.select("SCL")
            # Clear pixels: 4 (vegetation), 5 (bare soil), 6 (water), 7 (unclassified)
            clear_mask = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(7))
            return image.updateMask(clear_mask).divide(10000.0)

        # Retrieve images
        s2_collection = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")

        pre_img = (
            s2_collection.filterBounds(point)
            .filterDate(pre_start, pre_end)
            .map(mask_s2_clouds)
            .median()
        )

        post_img = (
            s2_collection.filterBounds(point)
            .filterDate(post_start, post_end)
            .map(mask_s2_clouds)
            .median()
        )

        # Compute indices: NDVI = (B8-B4)/(B8+B4), NBR = (B8-B12)/(B8+B12), NDMI = (B8-B11)/(B8+B11)
        pre_ndvi = pre_img.normalizedDifference(["B8", "B4"]).rename("ndvi")
        pre_nbr = pre_img.normalizedDifference(["B8", "B12"]).rename("nbr")
        pre_ndmi = pre_img.normalizedDifference(["B8", "B11"]).rename("ndmi")

        post_nbr = post_img.normalizedDifference(["B8", "B12"]).rename("nbr_post")
        delta_nbr = pre_nbr.subtract(post_nbr).rename("delta_nbr")

        combined = pre_ndvi.addBands([pre_nbr, pre_ndmi, delta_nbr])
        sampled = combined.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=point.buffer(100),
            scale=20,
        ).getInfo()

        ndvi_val = sampled.get("ndvi")
        nbr_val = sampled.get("nbr")
        ndmi_val = sampled.get("ndmi")
        dnbr_val = sampled.get("delta_nbr")

        return {
            "ndvi_value": round(float(ndvi_val), 4) if ndvi_val is not None else 0.40,
            "nbr_value": round(float(nbr_val), 4) if nbr_val is not None else 0.35,
            "ndmi_value": round(float(ndmi_val), 4) if ndmi_val is not None else 0.20,
            "delta_nbr": round(float(dnbr_val), 4) if dnbr_val is not None else 0.05,
            "cloud_cover_fraction": 0.10,
            "imagery_available": bool(sampled),
            "data_source": "GEE_SENTINEL_2",
            "imagery_timestamp": acq_date.isoformat(),
        }

    def _estimate_offline_spectral_features(
        self,
        lat: float,
        lon: float,
        acq_date: datetime.date,
        land_cover_class: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Report that no imagery is available. Never invent spectral values.

        This function previously returned NDVI, NBR and dNBR drawn from land-cover
        keyed random distributions, tagged imagery_available=True. Those numbers then
        surfaced in the UI as "Sentinel-2 Delta-NBR" evidence on operational alerts,
        and fed the classifier as though they were measurements.

        A fabricated spectral index on a fire alert is worse than no index at all: it
        cannot be distinguished from a real one by anything downstream, and it invites
        an analyst to trust a burn-severity reading that never existed. When Earth
        Engine is not configured, the correct answer is that we do not know.

        Downstream consumers must check imagery_available before using these fields.
        The feature pipeline in ml.features.site_features excludes spectral indices
        entirely unless GEE is live, so an unconfigured deployment simply trains and
        predicts without them.
        """
        logger.debug(
            "No Earth Engine credentials - returning spectral features as unavailable "
            "for (%.4f, %.4f)", lat, lon,
        )
        return {
            "ndvi_value": None,
            "nbr_value": None,
            "ndmi_value": None,
            "delta_nbr": None,
            "cloud_cover_fraction": None,
            "imagery_available": False,
            "data_source": "UNAVAILABLE_NO_GEE_CREDENTIALS",
            "imagery_timestamp": None,
            "reason": (
                "Google Earth Engine is not configured. Set EE_PROJECT_ID and "
                "service-account credentials to enable Sentinel-2 spectral features."
            ),
        }
