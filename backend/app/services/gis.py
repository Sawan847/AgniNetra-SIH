"""AgniNetra AI — GIS & Spatial Analysis Service.

Computes geospatial proximity, point-in-polygon containment, spatial density,
DBSCAN cluster spread/direction, and land cover intersection.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from sklearn.cluster import DBSCAN


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in kilometres."""
    r = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def find_nearest_facility(
    lat: float, lon: float, facilities: List[Dict[str, Any]]
) -> Tuple[float, Optional[Dict[str, Any]], bool]:
    """Find the nearest industrial facility and whether the point is directly inside (dist < 0.1km).

    Returns: (min_dist_km, nearest_facility_dict, is_inside_bool)
    """
    if not facilities:
        return 999.0, None, False

    min_dist = float("inf")
    nearest: Optional[Dict[str, Any]] = None

    for fac in facilities:
        f_lat = fac.get("latitude")
        f_lon = fac.get("longitude")
        if f_lat is None or f_lon is None:
            continue

        d = haversine_distance(lat, lon, float(f_lat), float(f_lon))
        if d < min_dist:
            min_dist = d
            nearest = fac

    if nearest is None:
        return 999.0, None, False

    is_inside = min_dist <= 0.15  # Within 150m is considered on-site/inside industrial zone
    return round(min_dist, 3), nearest, is_inside


def count_facilities_within_radius(
    lat: float, lon: float, facilities: List[Dict[str, Any]], radius_km: float
) -> int:
    """Count how many facilities exist within a given radius in kilometres."""
    count = 0
    for fac in facilities:
        f_lat = fac.get("latitude")
        f_lon = fac.get("longitude")
        if f_lat is not None and f_lon is not None:
            if haversine_distance(lat, lon, float(f_lat), float(f_lon)) <= radius_km:
                count += 1
    return count


def calculate_hotspot_spatial_density(
    lat: float, lon: float, other_hotspots: List[Dict[str, Any]], radius_km: float = 5.0
) -> float:
    """Calculate spatial density of thermal anomalies per square kilometre."""
    nearby_count = 0
    for h in other_hotspots:
        h_lat = h.get("latitude")
        h_lon = h.get("longitude")
        if h_lat is not None and h_lon is not None:
            d = haversine_distance(lat, lon, float(h_lat), float(h_lon))
            if 0.0 < d <= radius_km:
                nearby_count += 1

    area_sq_km = math.pi * (radius_km ** 2)
    return round(nearby_count / area_sq_km, 4)


def compute_cluster_spread_and_direction(
    hotspots: List[Dict[str, Any]], eps_km: float = 3.0, min_samples: int = 2
) -> List[Dict[str, Any]]:
    """Compute DBSCAN spatial clusters and return cluster size, spread radius (km), and direction (deg) for each hotspot."""
    if not hotspots:
        return []

    coords = np.array([[h["latitude"], h["longitude"]] for h in hotspots], dtype=float)
    kms_per_radian = 6371.0088
    epsilon = eps_km / kms_per_radian

    # Convert to radians for haversine metric
    rad_coords = np.radians(coords)
    db = DBSCAN(eps=epsilon, min_samples=min_samples, metric="haversine").fit(rad_coords)
    labels = db.labels_

    results = []
    for i, h in enumerate(hotspots):
        label = labels[i]
        if label == -1:  # Noise / singleton
            results.append({
                "cluster_size": 1,
                "cluster_spread_km": 0.0,
                "cluster_direction_deg": 0.0,
            })
        else:
            cluster_indices = np.where(labels == label)[0]
            cluster_coords = coords[cluster_indices]
            c_size = len(cluster_indices)

            # Compute spread (max pairwise distance from centroid)
            centroid_lat = np.mean(cluster_coords[:, 0])
            centroid_lon = np.mean(cluster_coords[:, 1])

            spread = 0.0
            for pt in cluster_coords:
                dist = haversine_distance(centroid_lat, centroid_lon, pt[0], pt[1])
                if dist > spread:
                    spread = dist

            # Compute principal direction of elongation
            direction_deg = 0.0
            if c_size >= 2:
                d_lat = cluster_coords[:, 0] - centroid_lat
                d_lon = cluster_coords[:, 1] - centroid_lon
                # Principal component
                cov = np.cov(d_lat, d_lon)
                if cov.shape == (2, 2):
                    eigvals, eigvecs = np.linalg.eig(cov)
                    principal_vec = eigvecs[:, np.argmax(eigvals)]
                    angle_rad = math.atan2(principal_vec[1], principal_vec[0])
                    direction_deg = (math.degrees(angle_rad) + 360.0) % 360.0

            results.append({
                "cluster_size": int(c_size),
                "cluster_spread_km": round(float(spread), 3),
                "cluster_direction_deg": round(float(direction_deg), 1),
            })

    return results
