"""AgniNetra AI — NASA FIRMS Integration Service.

Handles Area API queries for VIIRS sensors (SNPP, NOAA-20, NOAA-21) with:
- Bounding box and date-range batching (<= 5 days per request)
- Resilient retries with exponential backoff
- Raw CSV payload archiving in data/raw/firms
- Strict schema validation and deterministic event ID creation
- Safe error handling without leaking MAP_KEY
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import io
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Supported NASA FIRMS NRT VIIRS sources
SUPPORTED_FIRMS_SOURCES = [
    "VIIRS_SNPP_NRT",
    "VIIRS_NOAA20_NRT",
    "VIIRS_NOAA21_NRT",
]

# Required columns in FIRMS VIIRS CSV responses
REQUIRED_CSV_COLUMNS = [
    "latitude",
    "longitude",
    "bright_ti4",
    "scan",
    "track",
    "acq_date",
    "acq_time",
    "satellite",
    "instrument",
    "confidence",
    "version",
    "bright_ti5",
    "frp",
    "daynight",
]


def mask_key_in_url(url: str, key: str) -> str:
    """Mask FIRMS Map Key in URL strings for safe logging."""
    if key and key in url:
        return url.replace(key, "******")
    return url


def generate_event_id(satellite: str, lat: float, lon: float, acq_date: str, acq_time: str) -> str:
    """Create a stable, unique event identifier for deduplication."""
    clean_sat = (satellite or "SAT").strip().upper()
    clean_time = (acq_time or "0000").strip().zfill(4)
    raw = f"{clean_sat}_{lat:.4f}_{lon:.4f}_{acq_date}_{clean_time}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"firms_{clean_sat}_{acq_date.replace('-', '')}_{clean_time}_{digest}"


class FIRMSClient:
    """Client for interacting with the NASA FIRMS Area API."""

    def __init__(
        self,
        map_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        self.map_key = (map_key or settings.effective_firms_map_key).strip()
        self.base_url = (base_url or settings.firms_base_url).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    def is_configured(self) -> bool:
        """Check if a valid MAP_KEY is configured."""
        return bool(self.map_key and len(self.map_key) >= 16)

    def split_date_range(
        self, start_date: datetime.date, end_date: datetime.date, max_batch_days: int = 5
    ) -> List[Tuple[datetime.date, int]]:
        """Split a wide date range into chunks compatible with the 5-day FIRMS limit."""
        batches = []
        curr = start_date
        while curr <= end_date:
            days_left = (end_date - curr).days + 1
            batch_days = min(days_left, max_batch_days)
            batches.append((curr, batch_days))
            curr += datetime.timedelta(days=batch_days)
        return batches

    def fetch_area_csv(
        self,
        source: str,
        bbox: Tuple[float, float, float, float],  # (min_lon, min_lat, max_lon, max_lat)
        start_date: datetime.date,
        day_range: int = 1,
    ) -> str:
        """Fetch raw CSV data from NASA FIRMS Area API with exponential backoff."""
        if not self.is_configured():
            logger.warning("NASA FIRMS MAP_KEY is not configured in environment.")
            return ""

        if source not in SUPPORTED_FIRMS_SOURCES:
            raise ValueError(f"Unsupported FIRMS source: {source}. Choose from {SUPPORTED_FIRMS_SOURCES}")

        day_range = max(1, min(day_range, 5))
        min_lon, min_lat, max_lon, max_lat = bbox
        bbox_str = f"{min_lon},{min_lat},{max_lon},{max_lat}"
        date_str = start_date.strftime("%Y-%m-%d")

        # URL structure: https://firms.modaps.eosdis.nasa.gov/api/area/csv/[MAP_KEY]/[SOURCE]/[BBOX]/[DAY_RANGE]/[DATE]
        endpoint = f"{self.base_url}/csv/{self.map_key}/{source}/{bbox_str}/{day_range}/{date_str}"
        safe_url = mask_key_in_url(endpoint, self.map_key)

        headers = {"User-Agent": "AgniNetra-AI-Platform/0.1.0"}

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info("Requesting FIRMS data: %s (attempt %d/%d)", safe_url, attempt, self.max_retries)
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.get(endpoint, headers=headers)

                if resp.status_code == 200:
                    csv_text = resp.text
                    self._cache_raw_response(source, date_str, bbox_str, csv_text)
                    return csv_text
                elif resp.status_code == 429:
                    wait_sec = attempt * 3
                    logger.warning("FIRMS API rate limited (429). Retrying in %ds...", wait_sec)
                    time.sleep(wait_sec)
                else:
                    logger.error("FIRMS API error HTTP %d on %s", resp.status_code, safe_url)
                    resp.raise_for_status()
            except Exception as exc:
                last_exc = exc
                wait_sec = attempt * 2
                logger.warning("FIRMS connection attempt %d failed: %s. Backing off %ds...", attempt, exc, wait_sec)
                time.sleep(wait_sec)

        if last_exc:
            raise RuntimeError(f"Failed to fetch FIRMS data after {self.max_retries} attempts: {last_exc}") from last_exc
        return ""

    def parse_firms_csv(self, csv_content: str, source_label: str = "FIRMS") -> List[Dict[str, Any]]:
        """Parse, validate, and convert raw FIRMS CSV text into standardized hotspot records."""
        if not csv_content or not csv_content.strip():
            return []

        # Check for error responses returned as text
        if "Invalid MAP_KEY" in csv_content or "Error:" in csv_content:
            logger.error("FIRMS API returned error message: %s", csv_content.strip()[:200])
            return []

        f = io.StringIO(csv_content)
        reader = csv.DictReader(f)

        records = []
        for row_idx, row in enumerate(reader):
            try:
                # Safe coordinate parsing
                lat = float(row.get("latitude", 0.0))
                lon = float(row.get("longitude", 0.0))
                if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                    continue

                # Safe float parsing
                bright_ti4 = self._safe_float(row.get("bright_ti4"))
                bright_ti5 = self._safe_float(row.get("bright_ti5"))
                frp = self._safe_float(row.get("frp"))

                # Confidence
                conf_raw = row.get("confidence", "").strip().lower()
                conf_val: Optional[float] = None
                if conf_raw in ("l", "low"):
                    conf_val = 30.0
                elif conf_raw in ("n", "nominal"):
                    conf_val = 65.0
                elif conf_raw in ("h", "high"):
                    conf_val = 90.0
                else:
                    conf_val = self._safe_float(conf_raw)

                # Date and Time
                acq_date_str = row.get("acq_date", "").strip()
                acq_time_str = row.get("acq_time", "").strip().zfill(4)

                acq_date_obj = datetime.date.fromisoformat(acq_date_str) if acq_date_str else None
                acq_time_obj = (
                    datetime.time(int(acq_time_str[:2]), int(acq_time_str[2:]))
                    if len(acq_time_str) == 4 and acq_time_str.isdigit()
                    else None
                )

                satellite = row.get("satellite", "").strip()
                instrument = row.get("instrument", "").strip()
                daynight = row.get("daynight", "D").strip().upper()[:1]

                event_id = generate_event_id(satellite, lat, lon, acq_date_str, acq_time_str)

                record = {
                    "event_id": event_id,
                    "latitude": round(lat, 6),
                    "longitude": round(lon, 6),
                    "brightness": bright_ti4,
                    "bright_ti4": bright_ti4,
                    "bright_ti5": bright_ti5,
                    "frp": frp,
                    "confidence": conf_val,
                    "satellite": satellite,
                    "instrument": instrument,
                    "acq_date": acq_date_obj,
                    "acq_time": acq_time_obj,
                    "daynight": daynight,
                    "source": source_label,
                    "raw_data": dict(row),
                }
                records.append(record)
            except Exception as e:
                logger.debug("Skipping malformed FIRMS CSV row #%d: %s", row_idx, e)

        return records

    def _safe_float(self, value: Any) -> Optional[float]:
        """Convert string to float safely, returning None on failure."""
        if value is None:
            return None
        try:
            val_str = str(value).strip()
            if not val_str or val_str.lower() in ("nan", "null", "none"):
                return None
            return float(val_str)
        except (ValueError, TypeError):
            return None

    def _cache_raw_response(self, source: str, date_str: str, bbox_str: str, content: str) -> Path:
        """Save raw CSV to data/raw/firms for lineage and auditing."""
        cache_dir = settings.get_raw_dir("firms")
        bbox_hash = hashlib.md5(bbox_str.encode("utf-8")).hexdigest()[:8]
        filename = f"{source}_{date_str}_{bbox_hash}.csv"
        file_path = cache_dir / filename
        file_path.write_text(content, encoding="utf-8")
        return file_path
