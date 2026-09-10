"""AgniNetra AI — Comprehensive Feature Engineering Module.

Computes thermal, spatial proximity, historical persistence, DBSCAN cluster spread,
and satellite spectral features for the two-stage fire classification engine.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

from ml.config import FEATURE_COLUMNS


def compute_persistence_score(
    hotspots: pd.DataFrame,
    radius_km: float = 2.0,
    window_days: int = 7,
) -> pd.Series:
    """Count recurrence of thermal anomalies within a spatial radius over a temporal window."""
    if hotspots.empty:
        return pd.Series(dtype=float)

    result = np.zeros(len(hotspots), dtype=float)
    dates = pd.to_datetime(hotspots["acq_date"])
    lats = hotspots["latitude"].values
    lons = hotspots["longitude"].values

    for i in range(len(hotspots)):
        time_mask = (dates >= dates.iloc[i] - pd.Timedelta(days=window_days)) & (
            dates <= dates.iloc[i]
        )
        spatial_dist = _haversine_vectorized(lats[i], lons[i], lats, lons)
        nearby = (spatial_dist <= radius_km) & time_mask.values
        result[i] = max(int(nearby.sum()) - 1, 0)

    return pd.Series(result, index=hotspots.index, name=f"persistence_score_{window_days}d")


def compute_historical_frp_baselines(
    hotspots: pd.DataFrame,
    radius_km: float = 3.0,
    window_days: int = 90,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Compute historical median FRP, historical max FRP, and current-to-historical FRP ratio."""
    if hotspots.empty or "frp" not in hotspots.columns:
        empty = pd.Series(dtype=float)
        return empty, empty, empty

    n = len(hotspots)
    median_frp = np.zeros(n, dtype=float)
    max_frp = np.zeros(n, dtype=float)
    ratio_frp = np.ones(n, dtype=float)

    dates = pd.to_datetime(hotspots["acq_date"])
    lats = hotspots["latitude"].values
    lons = hotspots["longitude"].values
    frps = hotspots["frp"].fillna(0.0).values

    for i in range(n):
        time_mask = (dates >= dates.iloc[i] - pd.Timedelta(days=window_days)) & (
            dates < dates.iloc[i]  # strictly prior
        )
        spatial_dist = _haversine_vectorized(lats[i], lons[i], lats, lons)
        nearby_mask = (spatial_dist <= radius_km) & time_mask.values

        if nearby_mask.any():
            hist_vals = frps[nearby_mask]
            med = float(np.median(hist_vals))
            mx = float(np.max(hist_vals))
            median_frp[i] = round(med, 2)
            max_frp[i] = round(mx, 2)
            ratio_frp[i] = round(float(frps[i] / (med + 1e-3)), 2)
        else:
            median_frp[i] = round(float(frps[i]), 2)
            max_frp[i] = round(float(frps[i]), 2)
            ratio_frp[i] = 1.0

    return (
        pd.Series(median_frp, index=hotspots.index, name="historical_median_frp"),
        pd.Series(max_frp, index=hotspots.index, name="historical_max_frp"),
        pd.Series(ratio_frp, index=hotspots.index, name="frp_to_historical_ratio"),
    )


def compute_daynight_flag(hotspots: pd.DataFrame) -> pd.Series:
    """Convert FIRMS daynight column to boolean integer (1 for Night, 0 for Day)."""
    if "daynight" not in hotspots.columns:
        return pd.Series(0, index=hotspots.index, name="is_nighttime")
    return hotspots["daynight"].astype(str).str.upper().eq("N").astype(int).rename("is_nighttime")


def compute_day_of_year(hotspots: pd.DataFrame) -> pd.Series:
    """Extract day of year (1-366) from acquisition date."""
    if "acq_date" not in hotspots.columns:
        return pd.Series(1, index=hotspots.index, name="day_of_year")
    return pd.to_datetime(hotspots["acq_date"]).dt.dayofyear.rename("day_of_year")


def compute_cluster_spread_features(
    hotspots: pd.DataFrame,
    eps_km: float = 3.0,
    min_samples: int = 2,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Compute DBSCAN cluster size, spread radius (km), and principal elongation direction (deg)."""
    n = len(hotspots)
    if n == 0:
        empty = pd.Series(dtype=float)
        return empty, empty, empty

    coords = hotspots[["latitude", "longitude"]].values
    kms_per_radian = 6371.0088
    epsilon = eps_km / kms_per_radian

    rad_coords = np.radians(coords)
    db = DBSCAN(eps=epsilon, min_samples=min_samples, metric="haversine").fit(rad_coords)
    labels = db.labels_

    sizes = np.ones(n, dtype=int)
    spreads = np.zeros(n, dtype=float)
    directions = np.zeros(n, dtype=float)

    for i in range(n):
        lbl = labels[i]
        if lbl != -1:
            cluster_indices = np.where(labels == lbl)[0]
            c_coords = coords[cluster_indices]
            sizes[i] = len(cluster_indices)

            centroid = np.mean(c_coords, axis=0)
            dists = _haversine_vectorized(centroid[0], centroid[1], c_coords[:, 0], c_coords[:, 1])
            spreads[i] = round(float(np.max(dists)), 3)

            if len(cluster_indices) >= 2:
                d_lat = c_coords[:, 0] - centroid[0]
                d_lon = c_coords[:, 1] - centroid[1]
                cov = np.cov(d_lat, d_lon)
                if cov.shape == (2, 2):
                    eigvals, eigvecs = np.linalg.eigh(cov)
                    p_vec = eigvecs[:, np.argmax(eigvals)]
                    angle_deg = float(np.degrees(np.arctan2(float(p_vec[1]), float(p_vec[0]))) % 360.0)
                    directions[i] = round(angle_deg, 1)

    return (
        pd.Series(sizes, index=hotspots.index, name="cluster_size"),
        pd.Series(spreads, index=hotspots.index, name="cluster_spread_km"),
        pd.Series(directions, index=hotspots.index, name="cluster_direction_deg"),
    )


def extract_full_feature_vector(
    hotspot_record: Dict[str, Any],
    historical_hotspots: Optional[List[Dict[str, Any]]] = None,
    facilities: Optional[List[Dict[str, Any]]] = None,
    spectral_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, float]:
    """Extract a complete, standardized 37-dimensional feature dictionary for a single hotspot."""
    lat = float(hotspot_record.get("latitude", 0.0))
    lon = float(hotspot_record.get("longitude", 0.0))
    bright_ti4 = float(hotspot_record.get("bright_ti4") or hotspot_record.get("brightness") or 330.0)
    bright_ti5 = float(hotspot_record.get("bright_ti5") or (bright_ti4 - 15.0))
    frp = float(hotspot_record.get("frp") or 25.0)
    confidence = float(hotspot_record.get("confidence") or 80.0)

    daynight = str(hotspot_record.get("daynight", "D")).upper()
    is_nighttime = 1.0 if daynight == "N" else 0.0

    acq_date = hotspot_record.get("acq_date")
    if isinstance(acq_date, str):
        acq_date = datetime.date.fromisoformat(acq_date)
    elif not isinstance(acq_date, datetime.date):
        acq_date = datetime.date.today()
    day_of_year = float(acq_date.timetuple().tm_yday)

    # Infrastructure distances
    dist_facility = 999.0
    is_inside = 0.0
    fac_1km = 0
    fac_5km = 0
    if facilities:
        for f in facilities:
            f_lat = f.get("latitude")
            f_lon = f.get("longitude")
            if f_lat is not None and f_lon is not None:
                d = _haversine_single(lat, lon, float(f_lat), float(f_lon))
                if d < dist_facility:
                    dist_facility = d
                if d <= 1.0:
                    fac_1km += 1
                if d <= 5.0:
                    fac_5km += 1
        is_inside = 1.0 if dist_facility <= 0.15 else 0.0

    # Historical persistence & counts
    count_24h = 0
    count_7d = 0
    count_30d = 0
    count_90d = 0
    hist_frps = []
    if historical_hotspots:
        for h in historical_hotspots:
            h_lat = float(h.get("latitude", 0.0))
            h_lon = float(h.get("longitude", 0.0))
            d = _haversine_single(lat, lon, h_lat, h_lon)
            if d <= 5.0:
                h_date = h.get("acq_date")
                if isinstance(h_date, str):
                    h_date = datetime.date.fromisoformat(h_date)
                if isinstance(h_date, datetime.date):
                    delta_days = (acq_date - h_date).days
                    if 0 <= delta_days <= 1:
                        count_24h += 1
                    if 0 <= delta_days <= 7:
                        count_7d += 1
                    if 0 <= delta_days <= 30:
                        count_30d += 1
                    if 0 <= delta_days <= 90:
                        count_90d += 1
                        if h.get("frp"):
                            hist_frps.append(float(h["frp"]))

    p_score_7d = max(count_7d - 1, 0)
    p_score_30d = max(count_30d - 1, 0)
    recurrence_rate = round(p_score_30d / 30.0, 3)

    hist_med = float(np.median(hist_frps)) if hist_frps else frp
    hist_max = float(np.max(hist_frps)) if hist_frps else frp
    frp_ratio = round(frp / (hist_med + 1e-3), 2)

    # Spectral & Land-cover
    spectral = spectral_data or {}
    ndvi = float(spectral.get("ndvi_value", 0.35))
    nbr = float(spectral.get("nbr_value", 0.25))
    ndmi = float(spectral.get("ndmi_value", 0.15))
    delta_nbr = float(spectral.get("delta_nbr", 0.05))
    cloud_cov = float(spectral.get("cloud_cover_fraction", 0.10))
    imagery_avail = 1.0 if spectral.get("imagery_available", True) else 0.0

    # Land cover determination
    lc_class = float(hotspot_record.get("land_cover_class") or (50 if is_inside else 40))

    # Approximate distances to other land use types
    dist_forest = 0.2 if lc_class == 10 else (8.0 if is_inside else 2.5)
    dist_cropland = 0.1 if lc_class == 40 else (5.0 if is_inside else 1.0)
    dist_mine = 0.1 if lc_class == 60 else 12.0
    dist_settlement = 0.5 if is_inside else 3.5

    features = {
        "brightness": bright_ti4,
        "bright_ti4": bright_ti4,
        "bright_ti5": bright_ti5,
        "brightness_delta": round(bright_ti4 - bright_ti5, 2),
        "frp": frp,
        "confidence": confidence,
        "is_nighttime": is_nighttime,
        "day_of_year": day_of_year,
        "dist_nearest_facility": round(dist_facility, 3),
        "is_inside_facility": is_inside,
        "nearby_facility_count_1km": float(fac_1km),
        "nearby_facility_count_5km": float(fac_5km),
        "dist_nearest_forest": round(dist_forest, 3),
        "dist_nearest_cropland": round(dist_cropland, 3),
        "dist_nearest_mine": round(dist_mine, 3),
        "dist_nearest_settlement": round(dist_settlement, 3),
        "nearby_hotspot_count_24h": float(count_24h),
        "nearby_hotspot_count_7d": float(count_7d),
        "nearby_hotspot_count_30d": float(count_30d),
        "nearby_hotspot_count_90d": float(count_90d),
        "persistence_score": float(p_score_7d),
        "persistence_score_30d": float(p_score_30d),
        "recurrence_rate": recurrence_rate,
        "historical_median_frp": round(hist_med, 2),
        "historical_max_frp": round(hist_max, 2),
        "frp_to_historical_ratio": frp_ratio,
        "cluster_size": 1.0,
        "cluster_spread_km": 0.0,
        "cluster_direction_deg": 0.0,
        "spatial_density_5km": round(count_24h / (np.pi * 25.0), 4),
        "land_cover_class": lc_class,
        "ndvi_value": ndvi,
        "nbr_value": nbr,
        "ndmi_value": ndmi,
        "delta_nbr": delta_nbr,
        "cloud_cover_fraction": cloud_cov,
        "imagery_available": imagery_avail,
    }

    return features


def _haversine_single(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance between two single points in kilometres."""
    r = 6371.0
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon / 2.0) ** 2
    )
    return float(2.0 * r * np.arcsin(np.sqrt(a)))


def _haversine_vectorized(
    lat1: float, lon1: float, lat2: np.ndarray, lon2: np.ndarray
) -> np.ndarray:
    """Vectorized haversine distance in kilometres."""
    r = 6371.0
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon / 2.0) ** 2
    )
    return 2.0 * r * np.arcsin(np.sqrt(a))
