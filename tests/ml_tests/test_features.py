"""Unit tests for ML feature engineering functions."""

from __future__ import annotations

import numpy as np
import pandas as pd
from ml.features.engineering import (
    compute_day_of_year,
    compute_daynight_flag,
    compute_persistence_score,
    compute_cluster_spread_features,
    compute_historical_frp_baselines,
    extract_full_feature_vector,
)
from ml.config import FEATURE_COLUMNS


def test_compute_daynight_flag():
    df = pd.DataFrame({"daynight": ["D", "N", "d", "n"]})
    flags = compute_daynight_flag(df)
    assert flags.tolist() == [0, 1, 0, 1]


def test_compute_day_of_year():
    df = pd.DataFrame({"acq_date": ["2024-01-01", "2024-02-01", "2024-12-31"]})
    doy = compute_day_of_year(df)
    assert doy.iloc[0] == 1
    assert doy.iloc[1] == 32
    assert doy.iloc[2] == 366  # 2024 is leap year


def test_compute_persistence_score_empty():
    df = pd.DataFrame(columns=["latitude", "longitude", "acq_date"])
    scores = compute_persistence_score(df)
    assert len(scores) == 0


def test_compute_persistence_score_recurring():
    df = pd.DataFrame({
        "latitude": [22.47, 22.471, 28.00],  # first 2 are close (<2km)
        "longitude": [69.87, 69.871, 77.00],
        "acq_date": ["2024-09-01", "2024-09-03", "2024-09-02"],
    })
    scores = compute_persistence_score(df, radius_km=2.0, window_days=7)
    assert len(scores) == 3
    assert scores.iloc[1] >= 1.0
    assert scores.iloc[2] == 0.0


def test_compute_cluster_spread_features():
    df = pd.DataFrame({
        "latitude": [22.47, 22.472, 22.475, 28.00],
        "longitude": [69.87, 69.872, 69.875, 77.00],
    })
    sizes, spreads, directions = compute_cluster_spread_features(
        df, eps_km=3.0, min_samples=2
    )
    assert len(sizes) == 4
    assert len(spreads) == 4
    assert len(directions) == 4
    # Last point is far away, should be noise (cluster_size = 1)
    assert sizes.iloc[3] == 1


def test_compute_historical_frp_baselines():
    df = pd.DataFrame({
        "latitude": [22.47, 22.471, 22.47],
        "longitude": [69.87, 69.871, 69.87],
        "acq_date": ["2024-06-01", "2024-06-10", "2024-08-30"],
        "frp": [100.0, 200.0, 50.0],
    })
    median_frp, max_frp, ratio = compute_historical_frp_baselines(
        df, radius_km=3.0, window_days=90
    )
    assert len(median_frp) == 3
    # Second point should have first as historical baseline
    assert median_frp.iloc[1] == 100.0
    assert max_frp.iloc[1] == 100.0


def test_extract_full_feature_vector():
    record = {
        "latitude": 22.47,
        "longitude": 69.87,
        "brightness": 350.0,
        "bright_ti4": 350.0,
        "bright_ti5": 330.0,
        "frp": 120.0,
        "confidence": 90.0,
        "daynight": "N",
        "acq_date": "2024-09-10",
    }
    features = extract_full_feature_vector(record)

    # Should contain all FEATURE_COLUMNS
    for col in FEATURE_COLUMNS:
        assert col in features, f"Missing feature: {col}"

    assert features["brightness"] == 350.0
    assert features["is_nighttime"] == 1.0
    assert features["frp"] == 120.0
    assert len(features) == len(FEATURE_COLUMNS)
