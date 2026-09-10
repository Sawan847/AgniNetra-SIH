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
import time
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
# Never let an HTTP client log a URL that carries the FIRMS MAP_KEY in its path.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logger = logging.getLogger("build_dataset")

# India mainland bounding box (min_lon, min_lat, max_lon, max_lat)
INDIA_BBOX = (68.0, 6.0, 98.0, 38.0)


def fetch_firms(
    bbox: Tuple[float, float, float, float],
    start: datetime.date,
    days: int,
    sources: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Pull real FIRMS detections for the requested products.

    Defaults to the NRT feed. Pass SP products to reach a past burning season -
    India's agricultural and forest fire categories are strongly seasonal and simply
    do not appear in a monsoon-window NRT pull.
    """
    from app.services.firms import FIRMS_NRT_SOURCES, FIRMSClient

    sources = sources or FIRMS_NRT_SOURCES
    client = FIRMSClient()
    if not client.is_configured():
        logger.error(
            "FIRMS_MAP_KEY is not set. Get a free key at "
            "https://firms.modaps.eosdis.nasa.gov/api/map_key/ and put it in .env"
        )
        sys.exit(2)

    all_records: List[Dict[str, Any]] = []
    for source in sources:
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


def _tile_bbox(
    bbox: Tuple[float, float, float, float], step_deg: float
) -> List[Tuple[float, float, float, float]]:
    """Split a bounding box into a grid of smaller boxes."""
    min_lon, min_lat, max_lon, max_lat = bbox
    tiles: List[Tuple[float, float, float, float]] = []
    lat = min_lat
    while lat < max_lat:
        lon = min_lon
        while lon < max_lon:
            tiles.append((lon, lat, min(lon + step_deg, max_lon), min(lat + step_deg, max_lat)))
            lon += step_deg
        lat += step_deg
    return tiles


def fetch_osm(
    bbox: Tuple[float, float, float, float],
    tile_deg: float = 4.0,
    pause_s: float = 1.5,
) -> List[Dict[str, Any]]:
    """Pull industrial, mining and landfill infrastructure from OSM, tile by tile.

    A single Overpass query over a national bounding box does not complete - the
    public endpoint times out well before it can return every industrial way and
    relation in India. Tiling keeps each request inside Overpass's execution budget,
    and a failed tile costs only that tile rather than the whole ingest.

    For a production deployment the right answer is a Geofabrik PBF bulk-loaded with
    osm2pgsql; this keeps the live path usable without that dependency.
    """
    from app.services.osm import OverpassClient

    client = OverpassClient()
    tiles = _tile_bbox(bbox, tile_deg)
    logger.info(
        "Querying Overpass across %d tiles of %.0f deg (a single national query times out)",
        len(tiles), tile_deg,
    )

    seen: set = set()
    facilities: List[Dict[str, Any]] = []
    failed = 0

    for i, tile in enumerate(tiles, 1):
        try:
            elements = client.fetch_infrastructure(tile)
        except Exception as exc:
            failed += 1
            logger.warning("  tile %d/%d failed (%s)", i, len(tiles), str(exc)[:80])
            continue

        kept = 0
        for el in elements:
            lat = el.get("latitude") or el.get("lat")
            lon = el.get("longitude") or el.get("lon")
            if lat is None or lon is None:
                continue
            # OverpassClient.parse_overpass_elements returns the raw OSM tags under
            # "metadata", not "tags". Reading the wrong key silently produced an empty
            # tag dict for every element, so _categorise_osm returned None and every
            # facility in the country was discarded without a single warning.
            tags = el.get("metadata") or el.get("tags") or {}
            category = _categorise_osm(tags)
            if category is None:
                # Fall back to the coarse facility_type the client already derived,
                # so an element with unusual tagging is not lost outright.
                category = _categorise_facility_type(el.get("facility_type"))
            if category is None:
                continue
            # Tiles share edges, so the same feature can be returned twice.
            key = (round(float(lat), 5), round(float(lon), 5), category)
            if key in seen:
                continue
            seen.add(key)
            facilities.append({
                "name": tags.get("name", "unnamed"),
                "latitude": float(lat),
                "longitude": float(lon),
                "category": category,
            })
            kept += 1

        if kept:
            logger.info("  tile %d/%d -> +%d facilities (%d total)",
                        i, len(tiles), kept, len(facilities))
        time.sleep(pause_s)   # respect the public endpoint's rate limits

    if failed:
        logger.warning("%d of %d Overpass tiles failed", failed, len(tiles))
    if not facilities:
        logger.warning(
            "No OSM facilities retrieved. Infrastructure distance features will carry "
            "no signal and industrial classification will rely on thermal behaviour "
            "alone. Consider a smaller --bbox or a Geofabrik bulk load."
        )

    logger.info("Retained %d unique facilities", len(facilities))
    return facilities



def fetch_landcover(
    bbox: Tuple[float, float, float, float],
    tile_deg: float = 4.0,
    pause_s: float = 1.5,
) -> List[Dict[str, Any]]:
    """Pull forest / scrub / cropland centroids from OSM, tile by tile.

    FIRMS carries no land-cover field. Without this, every live detection has an
    unknown surface type, and the labelling rules that identify wildfire and crop
    residue burning - the "natural fires" half of deliverable (i) - cannot fire on
    the confirmed path at all.
    """
    from app.services.osm import OverpassClient

    client = OverpassClient()
    tiles = _tile_bbox(bbox, tile_deg)
    logger.info("Querying Overpass land cover across %d tiles", len(tiles))

    points: List[Dict[str, Any]] = []
    failed = 0
    for i, tile in enumerate(tiles, 1):
        try:
            pts = client.fetch_landcover(tile)
        except Exception as exc:
            failed += 1
            logger.warning("  landcover tile %d/%d failed (%s)", i, len(tiles), str(exc)[:70])
            continue
        if pts:
            points.extend(pts)
            logger.info("  landcover tile %d/%d -> +%d (%d total)",
                        i, len(tiles), len(pts), len(points))
        time.sleep(pause_s)

    if failed:
        logger.warning("%d of %d land-cover tiles failed", failed, len(tiles))
    if not points:
        logger.warning(
            "No land cover retrieved. Wildfire and crop-burning labels will rely on "
            "the behavioural fallback rules only."
        )
    return points


def _categorise_facility_type(facility_type: Any) -> Optional[str]:
    """Map OverpassClient's derived facility_type onto our three categories."""
    t = str(facility_type or "").lower()
    if not t:
        return None
    if "mining" in t or "quarry" in t:
        return "mine"
    if "landfill" in t or "waste" in t:
        return "landfill"
    if "industrial" in t or "power" in t or "refinery" in t or "works" in t:
        return "industrial"
    return None


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
    ap.add_argument("--sources", type=str, default=None,
                    help="comma-separated FIRMS products, e.g. VIIRS_SNPP_SP. "
                         "Defaults to the NRT feed; use SP products for past seasons.")
    ap.add_argument("--skip-landcover", action="store_true",
                    help="skip the OSM land-cover pass (faster; relies on fallback rules)")
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
        src_list = [x.strip() for x in args.sources.split(",")] if args.sources else None
        detections = fetch_firms(bbox, start, args.days, sources=src_list)  # type: ignore[arg-type]
        facilities = fetch_osm(bbox)  # type: ignore[arg-type]
        land_cover_points = (
            [] if args.skip_landcover else fetch_landcover(bbox)  # type: ignore[arg-type]
        )
        provenance = (
            f"NASA FIRMS {','.join(src_list) if src_list else 'NRT'} "
            f"bbox={args.bbox} start={start} days={args.days}; "
            f"OSM Overpass infrastructure + land cover"
        )
    else:
        from ml.data.simulate import build_facility_registry, simulate_detections
        logger.info("Using OFFLINE SIMULATION - real FIRMS schema, simulated behaviour")
        detections = simulate_detections()
        facilities = build_facility_registry()
        land_cover_points = []   # the simulator already supplies land_cover_class
        provenance = (
            "OFFLINE SIMULATION (ml.data.simulate). Real FIRMS schema and real Indian "
            "site coordinates; burn behaviour is simulated. NOT real observations."
        )

    logger.info("Detections: %d | Facilities: %d | Land-cover points: %d",
                len(detections), len(facilities), len(land_cover_points))

    from ml.training.train_pipeline import build_training_frame, train

    labelled = build_training_frame(
        detections, facilities=facilities, land_cover_points=land_cover_points
    )

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
