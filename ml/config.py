"""AgniNetra AI — Machine Learning Module Configuration Constants.

Defines the six standardized classification categories, two-stage hierarchy,
feature column definitions, and default model hyperparameters.
"""

from __future__ import annotations

# The six standardized platform classification categories
FIRE_CLASSES: list[str] = [
    "accidental_industrial_fire",
    "persistent_industrial_source",
    "forest_or_natural_fire",
    "agricultural_burning",
    "mining_or_other",
    "uncertain",
]

# Two-Stage Hierarchy Classes
STAGE1_CLASSES: list[str] = [
    "industrial",
    "forest_or_natural_fire",
    "agricultural_burning",
    "mining_or_other",
]

STAGE2_CLASSES: list[str] = [
    "persistent_industrial_source",
    "accidental_industrial_fire",
]

# Complete feature vector columns expected by the ML pipelines
FEATURE_COLUMNS: list[str] = [
    # Thermal properties
    "brightness",
    "bright_ti4",
    "bright_ti5",
    "brightness_delta",
    "frp",
    "confidence",
    # Temporal & Context
    "is_nighttime",
    "day_of_year",
    # Spatial proximity to infrastructure & land types
    "dist_nearest_facility",
    "is_inside_facility",
    "nearby_facility_count_1km",
    "nearby_facility_count_5km",
    "dist_nearest_forest",
    "dist_nearest_cropland",
    "dist_nearest_mine",
    "dist_nearest_settlement",
    # Temporal detection counts & persistence
    "nearby_hotspot_count_24h",
    "nearby_hotspot_count_7d",
    "nearby_hotspot_count_30d",
    "nearby_hotspot_count_90d",
    "persistence_score",
    "persistence_score_30d",
    "recurrence_rate",
    # Historical thermal baselines
    "historical_median_frp",
    "historical_max_frp",
    "frp_to_historical_ratio",
    # Cluster & Spatial spread
    "cluster_size",
    "cluster_spread_km",
    "cluster_direction_deg",
    "spatial_density_5km",
    # Land cover & Spectral indices
    "land_cover_class",
    "ndvi_value",
    "nbr_value",
    "ndmi_value",
    "delta_nbr",
    # Data quality
    "cloud_cover_fraction",
    "imagery_available",
]

# Default XGBoost hyperparameters
DEFAULT_XGBOOST_PARAMS: dict = {
    "n_estimators": 200,
    "max_depth": 5,
    "learning_rate": 0.08,
    "subsample": 0.85,
    "colsample_bytree": 0.85,
    "random_state": 42,
    "eval_metric": "logloss",
}

# Default Random Forest hyperparameters
DEFAULT_RF_PARAMS: dict = {
    "n_estimators": 150,
    "max_depth": 10,
    "min_samples_split": 4,
    "min_samples_leaf": 2,
    "random_state": 42,
    "class_weight": "balanced",
}

# Default HistGradientBoosting hyperparameters
DEFAULT_HGB_PARAMS: dict = {
    "max_iter": 150,
    "max_depth": 6,
    "learning_rate": 0.08,
    "random_state": 42,
    "class_weight": "balanced",
}

# Default Logistic Regression hyperparameters
DEFAULT_LR_PARAMS: dict = {
    "C": 1.0,
    "max_iter": 1000,
    "solver": "lbfgs",
    "random_state": 42,
    "class_weight": "balanced",
}
