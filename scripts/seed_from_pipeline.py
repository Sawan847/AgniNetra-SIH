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



def _parse_acq_time(raw) -> datetime.time:
    """Parse an acquisition time from either FIRMS' raw form or a round-tripped one.

    FIRMS CSV carries HHMM as a bare integer ("621", "0621"). Once that has been
    through the parser and written back out to CSV it becomes "06:21:00". The seeder
    must accept both, because it loads either raw simulator output or an already
    processed dataset.
    """
    t = str(raw or "").strip()
    if not t:
        return datetime.time(0, 0)
    if ":" in t:
        parts = t.split(":")
        try:
            return datetime.time(int(parts[0]) % 24, int(parts[1]) % 60)
        except (ValueError, IndexError):
            return datetime.time(0, 0)
    t = t.split(".")[0].zfill(4)
    try:
        return datetime.time(int(t[:2]) % 24, int(t[2:4]) % 60)
    except ValueError:
        return datetime.time(0, 0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="delete existing detections first")
    ap.add_argument("--limit", type=int, default=0, help="cap detections (0 = all)")
    ap.add_argument("--from-processed", type=str, default=None,
                    help="load an already-labelled dataset (data/processed/labelled_detections.csv) "
                         "instead of running the offline simulator - use this to seed real FIRMS data")
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

        if args.from_processed:
            # Real pipeline output: already clustered, feature-engineered and labelled
            # by scripts/build_dataset.py. Re-running the feature pipeline here would
            # recompute persistence from a truncated slice and silently disagree with
            # the model card.
            logger.info("Loading labelled dataset from %s", args.from_processed)
            feats_pre = pd.read_csv(args.from_processed, low_memory=False)
            if args.limit and len(feats_pre) > args.limit:
                # Systematic sample across the whole file, not head().
                #
                # The dataset is ordered by acquisition date, so head() returns only
                # the earliest days. On a March-April pull that means every row comes
                # from before 15 April - which is exactly when rabi stubble burning
                # starts - so the agricultural class vanishes from the seeded database
                # even though the pipeline labelled 24,417 of them.
                step = len(feats_pre) // args.limit + 1
                feats_pre = feats_pre.iloc[::step].head(args.limit)
                logger.info(
                    "Sampled every %dth row across the full date range (%s to %s)",
                    step, feats_pre["acq_date"].min(), feats_pre["acq_date"].max(),
                )
            detections = feats_pre
            # Reuse the cached Overpass result so Facility Monitoring is populated
            # with the same infrastructure the classifier actually measured against.
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location(
                    "bd", str(ROOT / "scripts" / "build_dataset.py")
                )
                bd = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(bd)
                facilities = bd.fetch_osm((68.0, 18.0, 88.0, 33.0), pause_s=0.0)
            except Exception as exc:
                logger.warning("Could not load OSM facilities (%s)", str(exc)[:80])
                facilities = []
        else:
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
                # Keyed on position, not name. osm_id is UNIQUE, and a huge share of
                # real OSM industrial features carry no name at all - hashing the name
                # collapsed every "unnamed" facility in the country onto one id and the
                # insert failed on the unique constraint.
                osm_id=f"osm_{f['latitude']:.6f}_{f['longitude']:.6f}_{f['category']}",
                location=f"POINT({f['longitude']} {f['latitude']})",
                source=f.get("source", "OSM_OVERPASS"),
                metadata_={"category": f["category"], "provenance": "OSM Overpass"},
            ))
            added_fac += 1
        db.commit()
        logger.info("Inserted %d facilities", added_fac)

        # --- features + classification over the whole archive at once ---
        if args.from_processed:
            feats = detections          # already engineered upstream
            logger.info("Using %d pre-engineered rows", len(feats))
        else:
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
            acq_t = _parse_acq_time(row.get("acq_time"))

            hs_id = uuid.uuid4()
            db.add(Hotspot(
                id=hs_id,
                event_id=str(row.get("event_id") or f"det_{i}_{acq.isoformat()}_{acq_t.strftime('%H%M')}"),
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
                raw_data={"site_name": row.get("site_name", ""), "provenance": "simulated"},
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
