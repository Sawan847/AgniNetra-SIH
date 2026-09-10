"""AgniNetra AI - Build a training dataset and fit the classifier.

Two data paths, one pipeline:

  --source firms   Pull real NASA FIRMS VIIRS detections for a bounding box and date
                   range, and real OSM infrastructure via Overpass. Requires
                   FIRMS_MAP_KEY in the environment (free, instant, from
                   https://firms.modaps.eosdis.nasa.gov/api/map_key/).

  --source sim     Offline simulation with the identical schema, for demos, CI and
                   machines with no network. Same feature engineering, same
                   labelling, same training code - only the input rows differ.

Everything downstream of ingestion is shared, so a demo run and a production run
exercise the same code.

Examples
--------
  python scripts/build_dataset.py --source sim

  python scripts/build_dataset.py --source firms \
      --bbox 68.0,6.0,98.0,38.0 --start 2025-10-01 --days 60
"""

from __future__ import annotations

import argparse
import datetime
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s"
)
logger = logging.getLogger("build_dataset")

# India mainland bounding box (min_lon, min_lat, max_lon, max_lat)
INDIA_BBOX = (68.0, 6.0, 98.0, 38.0)


def fetch_firms(
    bbox: Tuple[float, float, float, float],
    start: datetime.date,
    days: int,
) -> pd.DataFrame:
    """Pull real FIRMS VIIRS detections across all three platforms."""
    from app.services.firms import SUPPORTED_FIRMS_SOURCES, FIRMSClient

    client = FIRMSClient()
    if not client.is_configured():
        logger.error(
            "FIRMS_MAP_KEY is not set. Get a free key at "
            "https://firms.modaps.eosdis.nasa.gov/api/map_key/ and put it in .env"
        )
        sys.exit(2)

    all_records: List[Dict[str, Any]] = []
    for source in SUPPORTED_FIRMS_SOURCES:
        for batch_start, batch_days in client.split_date_range(
            start, start + datetime.timedelta(days=days - 1)
        ):
            logger.info("FIRMS %s from %s (+%dd)", source, batch_start, batch_days)
            try:
                csv_text = client.fetch_area_csv(source, bbox, batch_start, batch_days)
            except Exception as exc:
                logger.warning("  batch failed: %s", exc)
                continue
            recs = client.parse_firms_csv(csv_text, source_label=source)
            logger.info("  -> %d detections", len(recs))
            all_records.extend(recs)

    if not all_records:
        logger.error("FIRMS returned no detections. Check the key, bbox and dates.")
        sys.exit(3)

    df = pd.DataFrame(all_records)
    # Deduplicate: the three VIIRS platforms overlap, and adjacent date batches can
    # return the same detection twice.
    before = len(df)
    df = df.drop_duplicates(subset=["event_id"])
    logger.info("Deduplicated %d -> %d detections", before, len(df))

    df["acq_date"] = pd.to_datetime(df["acq_date"]).dt.date.astype(str)
    return df


def fetch_osm(bbox: Tuple[float, float, float, float]) -> List[Dict[str, Any]]:
    """Pull real industrial, mining and landfill infrastructure from OSM."""
    from app.services.osm import OverpassClient

    client = OverpassClient()
    logger.info("Querying Overpass for infrastructure in bbox %s", bbox)
    try:
        elements = client.fetch_infrastructure(bbox)
    except Exception as exc:
        logger.warning("Overpass query failed (%s). Continuing with no facilities - "
                       "spatial features will carry no signal.", exc)
        return []

    facilities: List[Dict[str, Any]] = []
    for el in elements:
        lat = el.get("latitude") or el.get("lat")
        lon = el.get("longitude") or el.get("lon")
        if lat is None or lon is None:
            continue
        tags = el.get("tags", {}) or {}
        category = _categorise_osm(tags)
        if category is None:
            continue
        facilities.append({
            "name": tags.get("name", "unnamed"),
            "latitude": float(lat),
            "longitude": float(lon),
            "category": category,
        })

    logger.info("Retained %d categorised facilities from %d OSM elements",
                len(facilities), len(elements))
    return facilities


def _categorise_osm(tags: Dict[str, Any]) -> Optional[str]:
    """Map raw OSM tags onto the three categories the features use."""
    landuse = str(tags.get("landuse", "")).lower()
    man_made = str(tags.get("man_made", "")).lower()
    amenity = str(tags.get("amenity", "")).lower()

    if landuse in ("quarry", "surface_mining") or "mine" in landuse:
        return "mine"
    if landuse == "landfill" or amenity == "waste_disposal":
        return "landfill"
    if (
        landuse == "industrial"
        or man_made in ("works", "petroleum_refinery")
        or "power" in tags
        or "industrial" in tags
    ):
        return "industrial"
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the AgniNetra training dataset.")
    ap.add_argument("--source", choices=["firms", "sim"], default="sim")
    ap.add_argument("--bbox", type=str, default=",".join(str(v) for v in INDIA_BBOX),
                    help="min_lon,min_lat,max_lon,max_lat")
    ap.add_argument("--start", type=str, default=None, help="YYYY-MM-DD")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--out", type=str, default="data/processed")
    ap.add_argument("--artifacts", type=str, default="ml/artifacts")
    ap.add_argument("--skip-train", action="store_true")
    args = ap.parse_args()

    bbox = tuple(float(v) for v in args.bbox.split(","))  # type: ignore[assignment]
    if len(bbox) != 4:
        ap.error("--bbox needs exactly 4 comma-separated numbers")

    os.makedirs(args.out, exist_ok=True)

    if args.source == "firms":
        start = (
            datetime.date.fromisoformat(args.start)
            if args.start
            else datetime.date.today() - datetime.timedelta(days=args.days)
        )
        detections = fetch_firms(bbox, start, args.days)  # type: ignore[arg-type]
        facilities = fetch_osm(bbox)  # type: ignore[arg-type]
        provenance = (
            f"NASA FIRMS VIIRS (SNPP/NOAA-20/NOAA-21) bbox={args.bbox} "
            f"start={start} days={args.days}; OSM Overpass infrastructure"
        )
    else:
        from ml.data.simulate import build_facility_registry, simulate_detections
        logger.info("Using OFFLINE SIMULATION - real FIRMS schema, simulated behaviour")
        detections = simulate_detections()
        facilities = build_facility_registry()
        provenance = (
            "OFFLINE SIMULATION (ml.data.simulate). Real FIRMS schema and real Indian "
            "site coordinates; burn behaviour is simulated. NOT real observations."
        )

    logger.info("Detections: %d | Facilities: %d", len(detections), len(facilities))

    from ml.training.train_pipeline import build_training_frame, train

    labelled = build_training_frame(detections, facilities=facilities)

    det_path = os.path.join(args.out, "labelled_detections.parquet")
    try:
        labelled.to_parquet(det_path, index=False)
    except Exception:
        det_path = os.path.join(args.out, "labelled_detections.csv")
        labelled.to_csv(det_path, index=False)
    logger.info("Wrote labelled dataset -> %s", det_path)

    if args.skip_train:
        return

    result = train(labelled, artifacts_dir=args.artifacts, data_provenance=provenance)
    card = result["card"]

    print("\n" + "=" * 66)
    print(f"  Model      : {card['algorithm']}")
    print(f"  Provenance : {card['data_provenance'][:60]}")
    print(f"  Coverage   : {card['label_coverage']['coverage']:.1%} "
          f"({card['label_coverage']['labelled']} of "
          f"{card['label_coverage']['total_detections']})")
    m = card["selected_model_metrics"]
    print(f"  Holdout F1 : {m['temporal_holdout_macro_f1']}")
    ab = card["feature_ablation"]
    print(f"  Ablation   : {ab['spatial_cv_macro_f1_all_features']} -> "
          f"{ab['spatial_cv_macro_f1_ablated']} with rule features withheld")
    print(f"  Artifacts  : {result['model_path']}")
    print("=" * 66 + "\n")


if __name__ == "__main__":
    main()
