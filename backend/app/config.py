"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration sourced from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Database ----
    database_url: str = (
        "postgresql://agnietra:agnietra_dev@localhost:5432/agnietra_db"
    )

    # ---- Application ----
    environment: str = "development"
    log_level: str = "INFO"
    secret_key: str = "dev-secret-change-in-production"

    # ---- CORS ----
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # ---- NASA FIRMS ----
    firms_map_key: str = ""
    firms_api_key: str = ""  # alias/fallback
    firms_base_url: str = "https://firms.modaps.eosdis.nasa.gov/api/area"

    # ---- OpenStreetMap ----
    osm_overpass_url: str = "https://overpass-api.de/api/interpreter"

    # ---- Google Earth Engine ----
    ee_project_id: str = ""
    ee_service_account: str = ""
    ee_private_key: str = ""
    ee_use_mock_when_missing: bool = True

    # ---- Storage Paths ----
    data_raw_dir: str = "data/raw"
    data_processed_dir: str = "data/processed"
    ml_artifacts_dir: str = "ml/artifacts"

    # ---- Classification & Alert Thresholds ----
    uncertain_threshold: float = 0.45
    critical_alert_threshold: float = 0.80

    @property
    def effective_firms_map_key(self) -> str:
        """Return the active FIRMS Map Key, prioritizing FIRMS_MAP_KEY over FIRMS_API_KEY."""
        return self.firms_map_key.strip() or self.firms_api_key.strip()

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    def get_raw_dir(self, subfolder: str = "") -> Path:
        """Return resolved path to raw data storage directory."""
        p = Path(self.data_raw_dir) / subfolder
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
