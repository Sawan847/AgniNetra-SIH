"""AgniNetra AI — OpenStreetMap Overpass Integration Service.

Queries the Overpass API for industrial infrastructure, refineries, power plants,
quarries/mines, and settlements with rate-limit respect and caching.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class OverpassClient:
    """Client for retrieving geospatial infrastructure from OpenStreetMap via Overpass API."""

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 3,
    ):
        self.endpoint_url = (endpoint_url or settings.osm_overpass_url).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    def build_industrial_query(self, bbox: Tuple[float, float, float, float]) -> str:
        """Construct an Overpass QL query for thermal/industrial infrastructure within a bbox.

        BBox format for Overpass: (min_lat, min_lon, max_lat, max_lon)
        """
        min_lon, min_lat, max_lon, max_lat = bbox
        bbox_str = f"{min_lat},{min_lon},{max_lat},{max_lon}"

        query = f"""
        [out:json][timeout:60];
        (
          node["landuse"="industrial"]({bbox_str});
          way["landuse"="industrial"]({bbox_str});
          relation["landuse"="industrial"]({bbox_str});

          node["power"="plant"]({bbox_str});
          way["power"="plant"]({bbox_str});
          relation["power"="plant"]({bbox_str});

          node["man_made"="works"]({bbox_str});
          way["man_made"="works"]({bbox_str});

          node["man_made"="petroleum_refinery"]({bbox_str});
          way["man_made"="petroleum_refinery"]({bbox_str});

          node["industrial"]({bbox_str});
          way["industrial"]({bbox_str});

          node["landuse"="quarry"]({bbox_str});
          way["landuse"="quarry"]({bbox_str});
          node["landuse"="surface_mining"]({bbox_str});
          way["landuse"="surface_mining"]({bbox_str});
        );
        out center body;
        >;
        out skel qt;
        """
        return query.strip()

    def build_landcover_query(self, bbox: Tuple[float, float, float, float]) -> str:
        """Overpass QL for surface type: forest, scrub, cropland, grassland.

        NASA's FIRMS product carries no land-cover field, so without this every
        detection arrives with an unknown surface type and the labelling rules that
        identify wildfire and crop residue burning cannot fire.

        Only ways and relations are requested, and only centroids are returned
        (`out center`). India has an enormous number of farmland polygons and asking
        for full geometry does not complete; a centroid is sufficient because the
        feature pipeline only needs a nearest-neighbour lookup.
        """
        min_lon, min_lat, max_lon, max_lat = bbox
        b = f"{min_lat},{min_lon},{max_lat},{max_lon}"
        return f"""
        [out:json][timeout:90];
        (
          way["natural"="wood"]({b});
          relation["natural"="wood"]({b});
          way["landuse"="forest"]({b});
          relation["landuse"="forest"]({b});

          way["natural"="scrub"]({b});

          way["landuse"="farmland"]({b});
          way["landuse"="orchard"]({b});
          way["landuse"="vineyard"]({b});

          way["landuse"="meadow"]({b});
          way["natural"="grassland"]({b});
        );
        out center tags;
        """.strip()

    def fetch_landcover(
        self, bbox: Tuple[float, float, float, float]
    ) -> List[Dict[str, Any]]:
        """Fetch land-cover centroids, returned as ESA WorldCover-style codes.

        Reuses the same request, retry and cache machinery as fetch_infrastructure,
        under a separate cache key so the two layers never collide.
        """
        query = self.build_landcover_query(bbox)
        min_lon, min_lat, max_lon, max_lat = bbox
        bbox_key = f"landcover_{min_lon}_{min_lat}_{max_lon}_{max_lat}"

        cached = self._load_cached_response(bbox_key)
        if cached is not None:
            return self._parse_landcover_elements(cached)

        headers = {
            "User-Agent": "AgniNetra-AI-Geospatial-Platform/0.1.0 (contact@agnietra.gov.in)",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        for attempt in range(1, self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(self.endpoint_url, data={"data": query}, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    self._cache_raw_response(bbox_key, data)
                    return self._parse_landcover_elements(data)
                if resp.status_code in (429, 504):
                    time.sleep(attempt * 5)
                    continue
                resp.raise_for_status()
            except Exception as exc:
                logger.warning("Land-cover tile attempt %d failed: %s", attempt, str(exc)[:80])
                time.sleep(attempt * 2)
        return []

    @staticmethod
    def _parse_landcover_elements(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Map OSM landuse/natural tags onto ESA WorldCover class codes.

        Codes match ml.labeling.weak_labels so the labelling rules read the same
        vocabulary whether the surface type came from OSM or from a WorldCover raster.
        """
        tag_to_code = {
            ("natural", "wood"): 10,
            ("landuse", "forest"): 10,
            ("natural", "scrub"): 20,
            ("natural", "grassland"): 30,
            ("landuse", "meadow"): 30,
            ("landuse", "farmland"): 40,
            ("landuse", "orchard"): 40,
            ("landuse", "vineyard"): 40,
        }
        out: List[Dict[str, Any]] = []
        for elem in raw.get("elements", []) or []:
            tags = elem.get("tags") or {}
            code = None
            for (k, v), c in tag_to_code.items():
                if tags.get(k) == v:
                    code = c
                    break
            if code is None:
                continue
            centre = elem.get("center") or {}
            lat = elem.get("lat") or centre.get("lat")
            lon = elem.get("lon") or centre.get("lon")
            if lat is None or lon is None:
                continue
            out.append({"latitude": float(lat), "longitude": float(lon), "land_cover_class": code})
        return out

    def fetch_infrastructure(
        self, bbox: Tuple[float, float, float, float]
    ) -> List[Dict[str, Any]]:
        """Query Overpass API for infrastructure elements within bounding box."""
        query = self.build_industrial_query(bbox)
        min_lon, min_lat, max_lon, max_lat = bbox
        bbox_key = f"{min_lon}_{min_lat}_{max_lon}_{max_lat}"

        cached = self._load_cached_response(bbox_key)
        if cached is not None:
            logger.info("Loaded OSM infrastructure from cache for bbox: %s", bbox)
            return self.parse_overpass_elements(cached)

        headers = {
            "User-Agent": "AgniNetra-AI-Geospatial-Platform/0.1.0 (contact@agnietra.gov.in)",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info("Querying Overpass API (attempt %d/%d)...", attempt, self.max_retries)
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(
                        self.endpoint_url,
                        data={"data": query},
                        headers=headers,
                    )

                if resp.status_code == 200:
                    data = resp.json()
                    self._cache_raw_response(bbox_key, data)
                    return self.parse_overpass_elements(data)
                elif resp.status_code == 429 or resp.status_code == 504:
                    wait_sec = attempt * 5
                    logger.warning("Overpass rate limited / busy (HTTP %d). Waiting %ds...", resp.status_code, wait_sec)
                    time.sleep(wait_sec)
                else:
                    logger.error("Overpass API returned HTTP %d", resp.status_code)
                    resp.raise_for_status()
            except Exception as exc:
                last_exc = exc
                wait_sec = attempt * 3
                logger.warning("Overpass attempt %d failed: %s. Backing off %ds...", attempt, exc, wait_sec)
                time.sleep(wait_sec)

        logger.error("Overpass query failed after %d retries: %s", self.max_retries, last_exc)
        return []

    def parse_overpass_elements(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse Overpass JSON elements into standardized facility records."""
        elements = raw_data.get("elements", [])
        facilities = []

        for elem in elements:
            tags = elem.get("tags", {})
            if not tags:
                continue

            elem_id = f"osm_{elem.get('type', 'node')}_{elem.get('id')}"
            name = tags.get("name") or tags.get("operator") or tags.get("description")

            # Determine facility type
            facility_type = "industrial"
            if "power" in tags and tags["power"] == "plant":
                facility_type = "power_plant"
            elif "industrial" in tags:
                facility_type = f"industrial_{tags['industrial']}"
            elif tags.get("landuse") in ("quarry", "surface_mining"):
                facility_type = "mining"
            elif "refinery" in tags or tags.get("man_made") == "petroleum_refinery":
                facility_type = "refinery"

            # Coordinate extraction
            lat = elem.get("lat") or (elem.get("center", {}).get("lat") if "center" in elem else None)
            lon = elem.get("lon") or (elem.get("center", {}).get("lon") if "center" in elem else None)

            if lat is None or lon is None:
                continue

            record = {
                "osm_id": elem_id,
                "name": name,
                "facility_type": facility_type,
                "latitude": float(lat),
                "longitude": float(lon),
                "location_wkt": f"POINT({lon} {lat})",
                "source": "OSM_OVERPASS",
                "metadata": tags,
            }
            facilities.append(record)

        return facilities

    def _cache_raw_response(self, bbox_key: str, data: Dict[str, Any]) -> Path:
        """Save Overpass JSON response to data/raw/osm for caching."""
        cache_dir = settings.get_raw_dir("osm")
        bbox_hash = hashlib.md5(bbox_key.encode("utf-8")).hexdigest()[:10]
        file_path = cache_dir / f"overpass_{bbox_hash}.json"
        file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return file_path

    def _load_cached_response(self, bbox_key: str) -> Optional[Dict[str, Any]]:
        """Load cached Overpass JSON response if available and recent (< 7 days old)."""
        cache_dir = settings.get_raw_dir("osm")
        bbox_hash = hashlib.md5(bbox_key.encode("utf-8")).hexdigest()[:10]
        file_path = cache_dir / f"overpass_{bbox_hash}.json"
        if file_path.exists():
            try:
                # Check modification time
                mtime = file_path.stat().st_mtime
                age_days = (time.time() - mtime) / (86400)
                if age_days < 7.0:
                    return json.loads(file_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.debug("Error reading OSM cache: %s", e)
        return None
