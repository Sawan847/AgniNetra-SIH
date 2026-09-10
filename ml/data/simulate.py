"""AgniNetra AI - Offline detection simulator for demonstration and CI.

WHAT THIS IS AND IS NOT
-----------------------
This module simulates *raw FIRMS detection records* - the same 14 columns NASA
returns - for a set of real Indian locations. It does NOT assign class labels.
Labels are always derived downstream by ml.labeling.weak_labels, exactly as they
are for live FIRMS data. Swapping this simulator for a real FIRMS pull changes the
input rows and nothing else in the pipeline.

The distinction matters. An earlier version of this project generated features
per-class from hand-written distributions, so the classifier learned to invert the
generator and its reported F1 measured nothing. Here the generator models physical
*processes* - a flare burns nightly for months, a wildfire burns for two days and
spreads - and the class must still be inferred from observed behaviour.

The `site_type` column is retained for one purpose only: measuring the precision of
the weak labelling functions against known infrastructure. It is never used as a
training label and never reaches the feature matrix.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Real Indian thermal sources. Coordinates are approximate site centroids, used so
# the demo map shows recognisable locations rather than random points in the sea.
KNOWN_SITES: List[Dict[str, Any]] = [
    # Every facility class named in SIH26162 is represented here: oil refineries,
    # petrochemical complexes, thermal power plants, steel industries, mining areas
    # and LNG terminals - plus the natural and agricultural sources the classifier
    # must segregate them from.
    #
    # (name, lat, lon, site_type, osm_category)

    # --- oil refineries ---
    {"name": "Jamnagar Refinery Complex", "lat": 22.350, "lon": 70.060, "site_type": "flare", "category": "industrial"},
    {"name": "Koyali Refinery, Vadodara", "lat": 22.350, "lon": 73.150, "site_type": "flare", "category": "industrial"},
    {"name": "Panipat Refinery & Petrochemical", "lat": 29.330, "lon": 76.970, "site_type": "flare", "category": "industrial"},

    # --- petrochemical complexes ---
    {"name": "Haldia Petrochemicals, WB", "lat": 22.050, "lon": 88.080, "site_type": "flare", "category": "industrial"},
    {"name": "Dahej Petrochemical Complex", "lat": 21.700, "lon": 72.580, "site_type": "flare", "category": "industrial"},

    # --- LNG terminals (boil-off gas flaring: episodic, not continuous) ---
    {"name": "Dahej LNG Terminal", "lat": 21.705, "lon": 72.530, "site_type": "lng", "category": "industrial"},
    {"name": "Hazira LNG Terminal", "lat": 21.100, "lon": 72.650, "site_type": "lng", "category": "industrial"},
    {"name": "Kochi LNG Terminal", "lat": 9.970, "lon": 76.250, "site_type": "lng", "category": "industrial"},

    # --- steel industries & thermal power ---
    {"name": "Bhilai Steel Plant", "lat": 21.210, "lon": 81.380, "site_type": "furnace", "category": "industrial"},
    {"name": "Rourkela Steel Plant", "lat": 22.230, "lon": 84.860, "site_type": "furnace", "category": "industrial"},
    {"name": "Tata Steel, Jamshedpur", "lat": 22.800, "lon": 86.190, "site_type": "furnace", "category": "industrial"},
    {"name": "Korba Thermal Power", "lat": 22.350, "lon": 82.680, "site_type": "furnace", "category": "industrial"},
    {"name": "Singrauli Power Complex", "lat": 24.200, "lon": 82.670, "site_type": "furnace", "category": "industrial"},
    {"name": "Ghazipur Landfill, Delhi", "lat": 28.620, "lon": 77.325, "site_type": "landfill", "category": "landfill"},
    {"name": "Deonar Landfill, Mumbai", "lat": 19.050, "lon": 72.930, "site_type": "landfill", "category": "landfill"},
    {"name": "Jharia Coalfield", "lat": 23.750, "lon": 86.420, "site_type": "mine", "category": "mine"},
    {"name": "Talcher Coalfield", "lat": 20.950, "lon": 85.230, "site_type": "mine", "category": "mine"},
    {"name": "Punjab Paddy Belt (Sangrur)", "lat": 30.250, "lon": 75.840, "site_type": "cropland", "category": None},
    {"name": "Haryana Wheat Belt (Karnal)", "lat": 29.690, "lon": 76.990, "site_type": "cropland", "category": None},
    {"name": "Uttarakhand Forest (Pauri)", "lat": 30.150, "lon": 78.780, "site_type": "forest", "category": None},
    {"name": "Similipal Forest, Odisha", "lat": 21.900, "lon": 86.400, "site_type": "forest", "category": None},
    {"name": "Bandipur Forest, Karnataka", "lat": 11.700, "lon": 76.500, "site_type": "forest", "category": None},
    {"name": "Bastar Forest, Chhattisgarh", "lat": 19.100, "lon": 82.020, "site_type": "forest", "category": None},
]

LC_BY_SITE_TYPE = {
    "flare": 50, "furnace": 50, "landfill": 50, "lng": 50,
    "mine": 60, "cropland": 40, "forest": 10,
}


def build_facility_registry() -> List[Dict[str, Any]]:
    """OSM-style facility records for the industrial, mine and landfill sites.

    Stands in for the OverpassClient output so the offline path exercises the same
    BallTree distance code that live OSM data would.
    """
    return [
        {
            "name": s["name"],
            "latitude": s["lat"],
            "longitude": s["lon"],
            "category": s["category"],
        }
        for s in KNOWN_SITES
        if s["category"] is not None
    ]


def simulate_detections(
    start_date: datetime.date = datetime.date(2024, 9, 1),
    n_days: int = 730,
    random_state: int = 42,
) -> pd.DataFrame:
    """Simulate FIRMS-schema detections by modelling each source's burn behaviour.

    Behaviour, not class, drives every value:
      flare    - fires nearly every night, stable modest FRP, very hot and pinned
      furnace  - most nights, day and night, moderate FRP
      landfill - recurrent but intermittent smouldering, low FRP
      mine     - persistent low-level coal seam heat
      cropland - short seasonal bursts, daytime, low FRP
      forest   - rare multi-day events that spread spatially

    One refinery is additionally given a two-day runaway incident, so the accident
    class exists in the data as a genuine departure from that site's own baseline
    rather than as a separately generated distribution.
    """
    rng = np.random.default_rng(random_state)
    rows: List[Dict[str, Any]] = []

    # Industrial accidents: each is a short, violent departure from that site's own
    # operating baseline. They are not drawn from a separate "accident" distribution -
    # the same site burns normally on every other day of the series, which is what
    # forces the model to learn the anomaly rather than memorise the location.
    # Spread across the whole series on purpose. The chronological holdout takes the
    # final 20% of days, so incidents clustered early would leave the accident class
    # with zero holdout support - unscoreable on exactly the category the system
    # exists to catch. Several deliberately fall inside the holdout window.
    incidents = {
        "Jamnagar Refinery Complex": (90, 2),      # refinery unit fire
        "Bhilai Steel Plant": (40, 2),             # steel plant blast
        "Koyali Refinery, Vadodara": (135, 1),
        "Tata Steel, Jamshedpur": (62, 2),
        "Korba Thermal Power": (152, 1),
        "Dahej LNG Terminal": (118, 1),            # LNG release + ignition
        "Haldia Petrochemicals, WB": (203, 2),     # petrochemical unit fire
        "Panipat Refinery & Petrochemical": (416, 2),
        "Rourkela Steel Plant": (612, 2),          # inside holdout window
        "Hazira LNG Terminal": (658, 1),           # inside holdout window
        "Dahej Petrochemical Complex": (701, 2),   # inside holdout window
    }

    for site in KNOWN_SITES:
        st = site["site_type"]

        for day in range(n_days):
            date = start_date + datetime.timedelta(days=day)
            doy = date.timetuple().tm_yday

            n_today, base_frp, ti4_lo, ti4_hi, night_p, jitter_km = _burn_profile(
                st, doy, rng
            )
            if n_today == 0:
                continue

            inc = incidents.get(site["name"])
            in_incident = inc is not None and inc[0] <= day < inc[0] + inc[1]
            if in_incident:
                n_today = int(rng.integers(6, 12))
                base_frp *= rng.uniform(12.0, 20.0)
                ti4_lo, ti4_hi = 400.0, 450.0

            for _ in range(n_today):
                is_night = rng.random() < night_p
                ti4 = float(rng.uniform(ti4_lo, ti4_hi))
                # I-5 sits closer to I-4 for large cool fire fronts and much lower
                # for small very hot sources.
                if st in ("flare",) or in_incident:
                    ti5 = ti4 - float(rng.uniform(28.0, 55.0))
                elif st in ("furnace", "mine", "landfill"):
                    ti5 = ti4 - float(rng.uniform(15.0, 30.0))
                else:
                    ti5 = ti4 - float(rng.uniform(5.0, 18.0))

                frp = float(max(0.5, rng.normal(base_frp, base_frp * 0.25)))

                rows.append({
                    "latitude": round(site["lat"] + float(rng.normal(0, jitter_km / 111.0)), 6),
                    "longitude": round(site["lon"] + float(rng.normal(0, jitter_km / 111.0)), 6),
                    "bright_ti4": round(ti4, 2),
                    "bright_ti5": round(ti5, 2),
                    "scan": round(float(rng.uniform(0.35, 0.6)), 2),
                    "track": round(float(rng.uniform(0.35, 0.6)), 2),
                    "acq_date": date.isoformat(),
                    "acq_time": f"{rng.integers(0, 24):02d}{rng.choice([0, 15, 30, 45]):02d}",
                    "satellite": str(rng.choice(["N", "N20", "N21"])),
                    "instrument": "VIIRS",
                    "confidence": str(rng.choice(["n", "h", "h", "h"])),
                    "version": "2.0NRT",
                    "frp": round(frp, 2),
                    "daynight": "N" if is_night else "D",
                    # retained only for measuring labelling-function precision
                    "site_type": st,
                    "site_name": site["name"],
                    "is_incident": int(in_incident),
                    "land_cover_class": LC_BY_SITE_TYPE[st],
                })

    df = pd.DataFrame(rows)
    logger.info(
        "Simulated %d detections across %d sites over %d days",
        len(df), len(KNOWN_SITES), n_days,
    )
    return df


def _burn_profile(
    site_type: str, doy: int, rng: np.random.Generator
) -> Tuple[int, float, float, float, float, float]:
    """Return (n_detections_today, base_frp, ti4_lo, ti4_hi, p_night, jitter_km)."""
    if site_type == "flare":
        # Burns nearly every night. Pinned to within ~200 m.
        n = int(rng.random() < 0.88) * int(rng.integers(1, 3))
        return n, 45.0, 345.0, 385.0, 0.85, 0.2

    if site_type == "lng":
        # Boil-off gas flaring at an LNG terminal is episodic, not continuous:
        # it spikes around tanker unloading and tank pressure management rather
        # than burning every night the way a refinery relief flare does. Lower
        # persistence than a flare, but the same small very-hot signature.
        n = int(rng.random() < 0.45) * int(rng.integers(1, 3))
        return n, 30.0, 340.0, 378.0, 0.80, 0.25

    if site_type == "furnace":
        n = int(rng.random() < 0.72) * int(rng.integers(1, 3))
        return n, 60.0, 335.0, 370.0, 0.55, 0.3

    if site_type == "landfill":
        n = int(rng.random() < 0.35) * int(rng.integers(1, 3))
        return n, 22.0, 325.0, 355.0, 0.45, 0.4

    if site_type == "mine":
        n = int(rng.random() < 0.55) * int(rng.integers(1, 4))
        return n, 35.0, 322.0, 358.0, 0.50, 0.6

    if site_type == "cropland":
        # Kharif (paddy) Oct-Nov, Rabi (wheat) Apr-May. Daytime, low FRP, bursty.
        in_season = (274 <= doy <= 334) or (105 <= doy <= 152)
        if not in_season:
            return 0, 0.0, 0.0, 0.0, 0.0, 0.0
        n = int(rng.random() < 0.75) * int(rng.integers(3, 14))
        return n, 18.0, 315.0, 345.0, 0.10, 1.8

    if site_type == "forest":
        # Rare, but when it happens it is large and spreads. Indian forest fire
        # season runs roughly Feb to mid-June.
        in_season = 32 <= doy <= 166
        p = 0.22 if in_season else 0.02
        if rng.random() >= p:
            return 0, 0.0, 0.0, 0.0, 0.0, 0.0
        n = int(rng.integers(6, 26))
        return n, 180.0, 350.0, 450.0, 0.35, 2.5

    return 0, 0.0, 0.0, 0.0, 0.0, 0.0


def expected_superclass_for_site_type(site_type: str) -> str:
    """Roll a site type up to the INDUSTRIAL / NATURAL / AGRICULTURAL axis.

    SIH26162 deliverable (i) is "classification and segregation of Industrial fires
    from forest fires and other natural fires", so this coarse axis is the primary
    thing the system is scored on. The five-class output refines it; it does not
    replace it.
    """
    return {
        "flare": "INDUSTRIAL", "lng": "INDUSTRIAL", "furnace": "INDUSTRIAL",
        "landfill": "INDUSTRIAL", "mine": "INDUSTRIAL",
        "cropland": "AGRICULTURAL",
        "forest": "NATURAL",
    }.get(site_type, "UNKNOWN")


def expected_class_for_site_type(site_type: str) -> str:
    """Map known infrastructure type to the class a correct labeller should assign.

    Used only to score labelling-function precision, never to train.
    """
    return {
        "flare": "persistent_industrial_source",
        "lng": "persistent_industrial_source",
        "furnace": "persistent_industrial_source",
        "landfill": "persistent_industrial_source",
        "mine": "mining_or_other",
        "cropland": "agricultural_burning",
        "forest": "forest_or_natural_fire",
    }.get(site_type, "unknown")
