"""AgniNetra AI — Demonstration Data Seeder.

IMPORTANT: This script is for DEMONSTRATION & LOCAL VERIFICATION ONLY.
All records inserted are clearly identified demo fixtures.
"""

from __future__ import annotations

import datetime
import logging
import sys
import uuid
from pathlib import Path

# Add backend and root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "backend"))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Handle SQLite geometry without SpatiaLite extension
try:
    import geoalchemy2.admin.dialects.sqlite as ga_sqlite
    ga_sqlite.after_create = lambda *args, **kwargs: None
    ga_sqlite.before_drop = lambda *args, **kwargs: None
    from geoalchemy2.types import _GISType
    _GISType.column_expression = lambda self, col: col
    _GISType.bind_expression = lambda self, val: val
except (ImportError, AttributeError):
    pass

from sqlalchemy import text
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models.alert import Alert
from app.models.facility import IndustrialFacility
from app.models.feedback import AnalystFeedback
from app.models.hotspot import Hotspot
from app.models.ingestion import AuditLog, IngestionRun
from app.models.land_cover import LandCover
from app.models.ml_model import ModelVersion
from app.models.prediction import HotspotFeature, Prediction
from app.models.user import User

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("seed_demo")


def seed_database() -> None:
    """Populate database with sample demonstration records across all 11 tables."""
    logger.info("Connecting to database: %s", settings.database_url)

    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        logger.warning("Table creation notice: %s", exc)

    db = SessionLocal()
    try:
        # Check if already seeded
        existing_user = db.query(User).filter(User.email == "analyst@agnietra.gov.in").first()
        if existing_user:
            logger.info("Demonstration data already seeded. Skipping.")
            return

        logger.info("Seeding demonstration data...")

        # 1. Ingestion Run
        ingestion_run = IngestionRun(
            id=uuid.uuid4(),
            source="FIRMS_VIIRS_SNPP",
            status="completed",
            records_fetched=25,
            records_inserted=25,
            records_skipped=0,
            started_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2),
            completed_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1, minutes=58),
        )
        db.add(ingestion_run)
        db.flush()

        # 2. User
        demo_user = User(
            id=uuid.uuid4(),
            email="analyst@agnietra.gov.in",
            hashed_password="$2b$12$eD4W1wQzZ0y.J7mB3h9Jv.1p6Z0kS7Q0Fv2nU9g1xZ4bJ9fA3w8qG",
            full_name="Dr. Alok Verma",
            role="analyst",
            is_active=True,
        )
        db.add(demo_user)
        db.flush()

        # 3. Model Version
        model_version = ModelVersion(
            id=uuid.uuid4(),
            model_name="AgniNetra-XGBoost-MultiClass",
            version="1.0.0-demo",
            algorithm="xgboost",
            hyperparameters={"n_estimators": 200, "max_depth": 6, "learning_rate": 0.1},
            metrics={"accuracy": 0.942, "macro_f1": 0.938},
            artifact_path="ml/artifacts/fire_classifier.joblib",
            is_active=True,
        )
        db.add(model_version)
        db.flush()

        # 4. Industrial Facilities
        facilities_data = [
            ("Jamnagar Refinery Complex", "refinery", "osm_jamnagar_001", 69.8700, 22.4700),
            ("Panipat Petrochemical Complex", "petrochemical", "osm_panipat_002", 76.9700, 29.3900),
            ("Korba Super Thermal Power Plant", "power_plant", "osm_korba_003", 82.6800, 22.3500),
            ("Tata Steel Jamshedpur Works", "steel_mill", "osm_jamshedpur_004", 86.2000, 22.8000),
        ]
        facilities = []
        for name, ftype, osm_id, lon, lat in facilities_data:
            fac = IndustrialFacility(
                id=uuid.uuid4(),
                name=name,
                facility_type=ftype,
                osm_id=osm_id,
                location=f"POINT({lon} {lat})",
                source="OSM_DEMO",
                metadata_={"operator": name.split()[0], "status": "active"},
            )
            db.add(fac)
            facilities.append(fac)
        db.flush()

        # 5. Land Cover Polygons
        land_covers = [
            (50, "Built-up", "POLYGON((69.80 22.40, 69.95 22.40, 69.95 22.55, 69.80 22.55, 69.80 22.40))"),
            (10, "Tree cover", "POLYGON((78.50 20.00, 78.80 20.00, 78.80 20.30, 78.50 20.30, 78.50 20.00))"),
            (40, "Cropland", "POLYGON((76.80 29.20, 77.10 29.20, 77.10 29.50, 76.80 29.50, 76.80 29.20))"),
        ]
        for c_class, label, poly_wkt in land_covers:
            lc = LandCover(
                id=uuid.uuid4(),
                cover_class=c_class,
                cover_label=label,
                geom=poly_wkt,
                year=2024,
                source="ESA_WorldCover_DEMO",
            )
            db.add(lc)
        db.flush()

        # 6. Sample Hotspots
        hotspot_scenarios = [
            {
                "lat": 22.4720, "lon": 69.8730, "bright": 395.4, "frp": 320.5, "conf": 95.0,
                "sat": "SNPP", "inst": "VIIRS", "daynight": "N",
                "pred_class": "accidental_industrial_fire", "conf_score": 0.94,
                "dist_fac": 0.15, "dist_road": 0.1, "dist_for": 8.5,
                "p_score": 1.0, "cov": 50,
                "alert_sev": "critical", "alert_type": "industrial_fire",
            },
            {
                "lat": 22.4690, "lon": 69.8680, "bright": 345.2, "frp": 65.0, "conf": 88.0,
                "sat": "SNPP", "inst": "VIIRS", "daynight": "N",
                "pred_class": "persistent_thermal_source", "conf_score": 0.97,
                "dist_fac": 0.05, "dist_road": 0.3, "dist_for": 9.0,
                "p_score": 12.0, "cov": 50,
                "alert_sev": "low", "alert_type": "flare_monitoring",
            },
            {
                "lat": 20.1500, "lon": 78.6500, "bright": 360.8, "frp": 210.0, "conf": 90.0,
                "sat": "NOAA-20", "inst": "VIIRS", "daynight": "D",
                "pred_class": "forest_natural_fire", "conf_score": 0.92,
                "dist_fac": 25.0, "dist_road": 4.5, "dist_for": 0.1,
                "p_score": 0.0, "cov": 10,
                "alert_sev": "high", "alert_type": "wildfire_alert",
            },
            {
                "lat": 29.3500, "lon": 76.9200, "bright": 328.0, "frp": 35.0, "conf": 75.0,
                "sat": "SNPP", "inst": "VIIRS", "daynight": "D",
                "pred_class": "agricultural_burning", "conf_score": 0.89,
                "dist_fac": 8.0, "dist_road": 0.8, "dist_for": 5.0,
                "p_score": 0.5, "cov": 40,
                "alert_sev": "medium", "alert_type": "stubble_burning",
            },
            {
                "lat": 22.3600, "lon": 82.6900, "bright": 338.5, "frp": 85.0, "conf": 82.0,
                "sat": "SNPP", "inst": "VIIRS", "daynight": "N",
                "pred_class": "mining_thermal", "conf_score": 0.86,
                "dist_fac": 1.2, "dist_road": 1.0, "dist_for": 3.0,
                "p_score": 4.0, "cov": 60,
                "alert_sev": "medium", "alert_type": "mining_activity",
            },
        ]

        for sc in hotspot_scenarios:
            h_id = uuid.uuid4()
            hotspot = Hotspot(
                id=h_id,
                latitude=sc["lat"],
                longitude=sc["lon"],
                geom=f"POINT({sc['lon']} {sc['lat']})",
                brightness=sc["bright"],
                frp=sc["frp"],
                confidence=sc["conf"],
                satellite=sc["sat"],
                instrument=sc["inst"],
                acq_date=datetime.date.today(),
                acq_time=datetime.time(14, 30),
                daynight=sc["daynight"],
                source="FIRMS_DEMO",
                ingestion_run_id=ingestion_run.id,
            )
            db.add(hotspot)
            db.flush()

            feat = HotspotFeature(
                id=uuid.uuid4(),
                hotspot_id=h_id,
                dist_nearest_facility=sc["dist_fac"],
                dist_nearest_road=sc["dist_road"],
                dist_nearest_forest=sc["dist_for"],
                nearby_hotspot_count_24h=2,
                nearby_hotspot_count_7d=5,
                persistence_score=sc["p_score"],
                land_cover_class=sc["cov"],
                ndvi_value=0.45,
                lst_delta=12.5,
                is_nighttime=(sc["daynight"] == "N"),
                day_of_year=datetime.date.today().timetuple().tm_yday,
            )
            db.add(feat)

            pred = Prediction(
                id=uuid.uuid4(),
                hotspot_id=h_id,
                model_version_id=model_version.id,
                predicted_class=sc["pred_class"],
                confidence_score=sc["conf_score"],
                class_probabilities={sc["pred_class"]: sc["conf_score"], "uncertain": round(1.0 - sc["conf_score"], 2)},
                feature_importances={"dist_nearest_facility": 0.35, "frp": 0.25, "persistence_score": 0.20},
            )
            db.add(pred)
            db.flush()

            alert = Alert(
                id=uuid.uuid4(),
                hotspot_id=h_id,
                prediction_id=pred.id,
                severity=sc["alert_sev"],
                alert_type=sc["alert_type"],
                status="active",
                description=f"Demonstration thermal alert ({sc['pred_class']}) near coordinate ({sc['lat']}, {sc['lon']})",
            )
            db.add(alert)

            if sc["pred_class"] == "accidental_industrial_fire":
                feedback = AnalystFeedback(
                    id=uuid.uuid4(),
                    prediction_id=pred.id,
                    user_id=demo_user.id,
                    corrected_class=None,
                    is_correct=True,
                    notes="Verified against on-site industrial sensor logs.",
                )
                db.add(feedback)

        audit = AuditLog(
            id=uuid.uuid4(),
            user_id=demo_user.id,
            action="seed_demonstration_data",
            resource_type="system",
            details={"notes": "Loaded SIH demonstration fixtures"},
        )
        db.add(audit)

        db.commit()
        logger.info("Successfully seeded demonstration fixtures across all 11 tables.")
    except Exception as e:
        db.rollback()
        logger.error("Error seeding database: %s", e)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
