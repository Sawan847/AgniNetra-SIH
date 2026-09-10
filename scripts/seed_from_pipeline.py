"""Load a full detection archive into the database for local demo and evaluation.

Seeds whatever the pipeline produces - simulated detections offline, or a real FIRMS
pull - together with the matching infrastructure registry, then runs classification
over every site and writes predictions and alerts.

Unlike scripts/seed_demo.py (a handful of illustrative fixtures with hardcoded
classes), every record here goes through the real feature and classification path.
Nothing is written that the model did not actually produce.

Usage:
    python scripts/seed_from_pipeline.py                 # offline simulation
    python scripts/seed_from_pipeline.py --reset         # wipe first
"""

from __future__ import annotations

import argparse
import datetime
import logging
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# geoalchemy2 needs neutering on SQLite, which has no SpatiaLite here.
try:
    import geoalchemy2.admin.dialects.sqlite as ga_sqlite
    ga_sqlite.after_create = lambda *a, **k: None
    ga_sqlite.before_drop = lambda *a, **k: None
    from geoalchemy2.types import _GISType
    _GISType.column_expression = lambda self, col: col
    _GISType.bind_expression = lambda self, val: val
except (ImportError, AttributeError):
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("seed_pipeline")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="delete existing detections first")
    ap.add_argument("--limit", type=int, default=0, help="cap detections (0 = all)")
    args = ap.parse_args()

    from app.database import Base, SessionLocal, engine
    from app.models.alert import Alert
    from app.models.facility import IndustrialFacility
    from app.models.hotspot import Hotspot
    from app.models.prediction import Prediction

    from ml.data.simulate import build_facility_registry, simulate_detections
    from ml.features.site_features import build_feature_frame
    from ml.training.train_pipeline import predict_with_abstention

    import joblib
    import pandas as pd

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        if args.reset:
            for model in (Alert, Prediction, Hotspot, IndustrialFacility):
                n = db.query(model).delete()
                logger.info("Deleted %d rows from %s", n, model.__tablename__)
            db.commit()

        detections = simulate_detections()
        if args.limit:
            detections = detections.head(args.limit)
        facilities = build_facility_registry()

        # --- facilities ---
        existing_names = {f.name for f in db.query(IndustrialFacility).all()}
        added_fac = 0
        for f in facilities:
            if f["name"] in existing_names:
                continue
            db.add(IndustrialFacility(
                id=uuid.uuid4(),
                name=f["name"],
                facility_type=f["category"],
                osm_id=f"demo_{abs(hash(f['name'])) % 10**9}",
                location=f"POINT({f['longitude']} {f['latitude']})",
                source="DEMO_REGISTRY",
                metadata_={"category": f["category"], "provenance": "offline simulation registry"},
            ))
            added_fac += 1
        db.commit()
        logger.info("Inserted %d facilities", added_fac)

        # --- features + classification over the whole archive at once ---
        logger.info("Engineering features over %d detections...", len(detections))
        feats = build_feature_frame(detections, facilities=facilities)

        bundle = joblib.load(ROOT / "ml" / "artifacts" / "thermal_classifier.joblib")
        logger.info("Classifying...")
        scores = predict_with_abstention(bundle, feats)

        # --- detections + predictions + alerts ---
        logger.info("Writing detections...")
        n_alerts = 0
        for i, (_, row) in enumerate(feats.iterrows()):
            s = scores[i]
            acq = datetime.date.fromisoformat(str(row["acq_date"]))
            t_raw = str(row.get("acq_time", "0000")).zfill(4)
            acq_t = datetime.time(int(t_raw[:2]) % 24, int(t_raw[2:]) % 60)

            hs_id = uuid.uuid4()
            db.add(Hotspot(
                id=hs_id,
                event_id=f"sim_{i}_{acq.isoformat()}_{t_raw}",
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                geom=f"POINT({row['longitude']} {row['latitude']})",
                brightness=float(row["bright_ti4"]),
                bright_ti4=float(row["bright_ti4"]),
                bright_ti5=float(row["bright_ti5"]),
                frp=float(row["frp"]),
                confidence=90.0 if str(row.get("confidence")) == "h" else 65.0,
                satellite=str(row.get("satellite", "N")),
                instrument="VIIRS",
                acq_date=acq,
                acq_time=acq_t,
                daynight=str(row.get("daynight", "D"))[:1],
                source="OFFLINE_SIMULATION",
                raw_data={"site_name": row.get("site_name"), "provenance": "simulated"},
            ))

            pred_id = uuid.uuid4()
            db.add(Prediction(
                id=pred_id,
                hotspot_id=hs_id,
                predicted_class=s["predicted_class"],
                confidence_score=float(s["confidence"]),
                stage1_class=s["predicted_class"],
                class_probabilities=s["class_probabilities"],
                feature_importances={},
                predicted_at=datetime.datetime.now(datetime.timezone.utc),
            ))

            # Alerts only for genuine incidents the model committed to.
            if s["predicted_class"] == "accidental_industrial_fire" and s["confidence"] >= 0.70:
                base = row.get("site_frp_median") or 0.0
                z = row.get("frp_zscore_at_site") or 0.0
                db.add(Alert(
                    id=uuid.uuid4(),
                    hotspot_id=hs_id,
                    prediction_id=pred_id,
                    severity="critical",
                    alert_type="accidental_industrial_fire",
                    status="active",
                    description=(
                        f"CRITICAL: anomalous thermal event at {row.get('site_name', 'unknown site')} "
                        f"({row['latitude']:.4f}, {row['longitude']:.4f}). "
                        f"FRP {float(row['frp']):.0f} MW against a site baseline of {float(base):.0f} MW "
                        f"({float(z):.0f} sigma above normal operation)."
                    ),
                    metadata_={
                        "site_frp_median": float(base),
                        "frp_zscore": float(z),
                        "persistence_ratio": float(row.get("persistence_ratio") or 0.0),
                    },
                ))
                n_alerts += 1

            if (i + 1) % 2000 == 0:
                db.commit()
                logger.info("  %d / %d", i + 1, len(feats))

        db.commit()

        counts = pd.Series([s["predicted_class"] for s in scores]).value_counts()
        logger.info("Seeded %d detections, %d alerts", len(feats), n_alerts)
        print("\nClass distribution written to DB:")
        for cls, n in counts.items():
            print(f"  {cls:32s} {n}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
