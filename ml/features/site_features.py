"""AgniNetra AI - Site-level spatiotemporal feature engineering.

Classification happens at the level of a *site*, not a pixel. A single VIIRS
detection carries almost no information about what produced it: a refinery flare
and a burning field can look nearly identical in one frame. What separates them is
behaviour over time - does this location burn every night for months, or once?

So the pipeline is:

    detections -> DBSCAN spatial clustering -> per-site temporal statistics
               -> real distances to OSM infrastructure -> features

All distance computations use a BallTree with the haversine metric, which is
O(n log n). The previous per-row Python loop was O(n-squared) and would not finish
on a national-scale detection archive.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.neighbors import BallTree

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0088

# VIIRS I-band nominal resolution is 375 m. Detections from the same fixed source
# scatter by roughly one pixel between overpasses due to geolocation and viewing
# geometry, so ~500 m groups a single physical source without merging neighbours.
DEFAULT_CLUSTER_EPS_KM = 0.5

# Distance beyond which we stop caring; keeps "no facility anywhere near" from
# becoming an unbounded feature value that dominates tree splits.
MAX_DIST_KM = 50.0


def assign_sites(
    df: pd.DataFrame,
    eps_km: float = DEFAULT_CLUSTER_EPS_KM,
    min_samples: int = 1,
) -> pd.DataFrame:
    """Cluster detections into physical sites using haversine DBSCAN.

    min_samples=1 means an isolated detection becomes its own single-member site
    rather than being discarded as noise - a one-off wildfire is still a site.
    """
    out = df.copy()
    if out.empty:
        out["site_id"] = []
        return out

    coords_rad = np.radians(out[["latitude", "longitude"]].to_numpy(dtype=float))
    eps_rad = eps_km / EARTH_RADIUS_KM

    labels = DBSCAN(
        eps=eps_rad, min_samples=min_samples, metric="haversine", algorithm="ball_tree"
    ).fit_predict(coords_rad)

    out["site_id"] = labels
    logger.info(
        "Clustered %d detections into %d sites (eps=%.0f m)",
        len(out),
        len(set(labels)),
        eps_km * 1000,
    )
    return out


def compute_site_statistics(df: pd.DataFrame) -> pd.DataFrame:
    """Compute per-site temporal behaviour - the features that actually separate
    infrastructure from events.

    persistence_ratio is the key one: the fraction of distinct days on which the
    site was detected, over the span it was observed. A gas flare approaches 1.0.
    A wildfire is a single day, so approaches 0.
    """
    if df.empty:
        return df.assign(
            persistence_ratio=[], site_n_detections=[], site_n_days=[],
            site_lifetime_days=[], site_frp_median=[], site_frp_std=[], site_frp_sigma_robust=[],
            site_frp_cv=[], centroid_drift_km=[], cluster_size=[],
            cluster_spread_km=[], site_night_fraction=[],
        )

    work = df.copy()
    work["_date"] = pd.to_datetime(work["acq_date"])

    stats: Dict[Any, Dict[str, float]] = {}

    for site_id, grp in work.groupby("site_id"):
        n_det = len(grp)
        n_days = int(grp["_date"].dt.normalize().nunique())
        span_days = int((grp["_date"].max() - grp["_date"].min()).days) + 1

        # Persistence: distinct active days over observed span. A site seen once is
        # 1/1 = 1.0 by that formula, which is wrong - a single sighting is no
        # evidence of persistence at all. Require a real span before crediting it.
        persistence = (n_days / span_days) if span_days > 1 else 0.0

        frp_vals = pd.to_numeric(grp.get("frp"), errors="coerce").dropna()
        frp_median = float(frp_vals.median()) if len(frp_vals) else 0.0
        frp_std = float(frp_vals.std(ddof=0)) if len(frp_vals) > 1 else 0.0
        frp_cv = float(frp_std / frp_median) if frp_median > 0 else 0.0

        # Robust scale via median absolute deviation. The sample standard deviation
        # is useless as an anomaly baseline here because the anomaly is inside the
        # sample: a two-day refinery fire inflates the site's own sigma enough that
        # the fire no longer clears a 4-sigma bar. MAD ignores the tail, so the
        # baseline describes normal operation rather than normal-plus-incident.
        # 1.4826 rescales MAD to be a consistent estimator of sigma for Gaussian data.
        if len(frp_vals) > 2:
            mad = float((frp_vals - frp_median).abs().median())
            frp_sigma_robust = 1.4826 * mad
        else:
            frp_sigma_robust = frp_std

        lats = grp["latitude"].to_numpy(dtype=float)
        lons = grp["longitude"].to_numpy(dtype=float)
        c_lat, c_lon = float(lats.mean()), float(lons.mean())
        dists = _haversine_to_point(lats, lons, c_lat, c_lon)
        drift = float(dists.mean()) if len(dists) else 0.0
        spread = float(dists.max()) if len(dists) else 0.0

        if "daynight" in grp.columns:
            night_frac = float(
                grp["daynight"].astype(str).str.upper().str.startswith("N").mean()
            )
        else:
            night_frac = float(grp.get("is_nighttime", pd.Series([0])).mean())

        stats[site_id] = {
            "persistence_ratio": round(persistence, 4),
            "site_n_detections": float(n_det),
            "site_n_days": float(n_days),
            "site_lifetime_days": float(span_days),
            "site_frp_median": round(frp_median, 3),
            "site_frp_std": round(frp_std, 3),
            "site_frp_sigma_robust": round(frp_sigma_robust, 3),
            "site_frp_cv": round(frp_cv, 4),
            "centroid_drift_km": round(drift, 4),
            "cluster_size": float(n_det),
            "cluster_spread_km": round(spread, 4),
            "site_night_fraction": round(night_frac, 4),
        }

    stat_df = pd.DataFrame.from_dict(stats, orient="index")
    stat_df.index.name = "site_id"

    merged = df.merge(stat_df, left_on="site_id", right_index=True, how="left")
    return merged


def add_infrastructure_distances(
    df: pd.DataFrame,
    facilities: Optional[Sequence[Dict[str, Any]]],
    category_field: str = "category",
) -> pd.DataFrame:
    """Compute true great-circle distance to the nearest facility of each category.

    These are measurements against real OSM geometry. They are NOT derived from
    land-cover class - an earlier version of this pipeline inferred them from the
    land-cover code, which made four separate "spatial" features into re-encodings
    of a single variable and leaked the answer into the input.

    Categories map onto the OSM tags fetched by OverpassClient:
      industrial -> landuse=industrial, man_made=works, petroleum_refinery, power=plant
      mine       -> landuse=quarry, landuse=surface_mining
      landfill   -> landuse=landfill, amenity=waste_disposal
    """
    out = df.copy()
    categories = ["industrial", "mine", "landfill"]

    for cat in categories:
        out["dist_" + cat + "_km"] = MAX_DIST_KM
        out["count_" + cat + "_5km"] = 0.0

    if out.empty:
        return out

    if not facilities:
        logger.warning(
            "No OSM facilities supplied - infrastructure distances default to %.0f km. "
            "Ingest OSM before training or the spatial features carry no signal.",
            MAX_DIST_KM,
        )
        return out

    det_rad = np.radians(out[["latitude", "longitude"]].to_numpy(dtype=float))

    for cat in categories:
        pts = [
            (float(f["latitude"]), float(f["longitude"]))
            for f in facilities
            if f.get("latitude") is not None
            and f.get("longitude") is not None
            and _matches_category(f.get(category_field), cat)
        ]
        if not pts:
            continue

        fac_rad = np.radians(np.asarray(pts, dtype=float))
        tree = BallTree(fac_rad, metric="haversine")

        dist_rad, _ = tree.query(det_rad, k=1)
        out["dist_" + cat + "_km"] = np.minimum(
            dist_rad[:, 0] * EARTH_RADIUS_KM, MAX_DIST_KM
        ).round(4)

        within = tree.query_radius(det_rad, r=5.0 / EARTH_RADIUS_KM, count_only=True)
        out["count_" + cat + "_5km"] = within.astype(float)

    out["is_inside_industrial"] = (out["dist_industrial_km"] <= 0.3).astype(float)
    return out


def _matches_category(raw: Any, category: str) -> bool:
    """Map a facility's OSM-derived type string onto a coarse category."""
    if raw is None:
        return category == "industrial"  # untyped facilities default to industrial
    text = str(raw).lower()
    if category == "industrial":
        return any(
            k in text
            for k in ("industrial", "works", "refinery", "power", "factory", "plant")
        )
    if category == "mine":
        return any(k in text for k in ("quarry", "mine", "mining"))
    if category == "landfill":
        return any(k in text for k in ("landfill", "waste", "dump"))
    return False


def add_thermal_features(df: pd.DataFrame) -> pd.DataFrame:
    """Per-detection radiometric and temporal features.

    brightness_delta (I-4 minus I-5) is the physically meaningful one: a small,
    very hot source such as a gas flare shows a large separation between the 4 um
    and 11 um brightness temperatures, while a large cooler fire front does not.
    """
    out = df.copy()
    if out.empty:
        return out

    ti4 = pd.to_numeric(out.get("bright_ti4"), errors="coerce")
    ti5 = pd.to_numeric(out.get("bright_ti5"), errors="coerce")

    out["bright_ti4"] = ti4
    out["bright_ti5"] = ti5
    out["brightness_delta"] = (ti4 - ti5).round(3)
    out["frp"] = pd.to_numeric(out.get("frp"), errors="coerce")
    out["confidence"] = pd.to_numeric(out.get("confidence"), errors="coerce")

    dates = pd.to_datetime(out["acq_date"])
    out["day_of_year"] = dates.dt.dayofyear.astype(float)

    if "daynight" in out.columns:
        out["is_nighttime"] = (
            out["daynight"].astype(str).str.upper().str.startswith("N").astype(float)
        )
    else:
        out["is_nighttime"] = 0.0

    # How far this detection sits above its own site's historical baseline. This is
    # the accident discriminator: routine flaring sits at ~1.0, an incident spikes.
    base = out.get("site_frp_median", pd.Series(0.0, index=out.index)).fillna(0.0)
    out["frp_to_site_baseline"] = (out["frp"].fillna(0.0) / (base + 1e-3)).round(3)

    sigma = out.get("site_frp_sigma_robust", pd.Series(0.0, index=out.index)).fillna(0.0)
    out["frp_zscore_at_site"] = (
        (out["frp"].fillna(0.0) - base) / (sigma + 1e-3)
    ).round(3)

    return out


def build_feature_frame(
    detections: pd.DataFrame,
    facilities: Optional[Sequence[Dict[str, Any]]] = None,
    land_cover: Optional[pd.Series] = None,
    eps_km: float = DEFAULT_CLUSTER_EPS_KM,
) -> pd.DataFrame:
    """Full feature pipeline: cluster, characterise, locate, and describe.

    This is the single entry point used by both training and inference, which is
    what keeps the two from drifting apart.
    """
    if detections.empty:
        return detections

    df = assign_sites(detections, eps_km=eps_km)
    df = compute_site_statistics(df)
    df = add_infrastructure_distances(df, facilities)
    df = add_thermal_features(df)

    if land_cover is not None:
        df["land_cover_class"] = land_cover.reindex(df.index).fillna(0).astype(float)
    elif "land_cover_class" not in df.columns:
        df["land_cover_class"] = 0.0

    # burn_scar_within_30d is populated by the MCD64A1 join when available; absent
    # that product the corresponding labelling function simply never fires.
    if "burn_scar_within_30d" not in df.columns:
        df["burn_scar_within_30d"] = 0

    return df


def _haversine_to_point(
    lats: np.ndarray, lons: np.ndarray, lat0: float, lon0: float
) -> np.ndarray:
    """Vectorised great-circle distance in km from an array of points to one point."""
    dlat = np.radians(lats - lat0)
    dlon = np.radians(lons - lon0)
    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(np.radians(lat0)) * np.cos(np.radians(lats)) * np.sin(dlon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


# Feature columns consumed by the model. Every one of these is either measured from
# the FIRMS record, computed from real detection history, or measured against real
# OSM geometry. None is imputed from another feature.
SITE_FEATURE_COLUMNS: List[str] = [
    # radiometric
    "bright_ti4",
    "bright_ti5",
    "brightness_delta",
    "frp",
    "confidence",
    # temporal
    "is_nighttime",
    "day_of_year",
    # site behaviour
    "persistence_ratio",
    "site_n_detections",
    "site_n_days",
    "site_lifetime_days",
    "site_frp_median",
    "site_frp_std",
    "site_frp_sigma_robust",
    "site_frp_cv",
    "centroid_drift_km",
    "cluster_size",
    "cluster_spread_km",
    "site_night_fraction",
    # anomaly relative to own baseline
    "frp_to_site_baseline",
    "frp_zscore_at_site",
    # real infrastructure geometry
    "dist_industrial_km",
    "dist_mine_km",
    "dist_landfill_km",
    "count_industrial_5km",
    "count_mine_5km",
    "count_landfill_5km",
    "is_inside_industrial",
    # context
    "land_cover_class",
]
