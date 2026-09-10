"""Compare AgniNetra's classification against NASA FIRMS' own `type` field.

SIH26162 opens with the claim that FIRMS "provides thermal anomaly detections but
does not distinguish between industrial fires, gas flares, agricultural burning,
mining activity, and wildfires." FIRMS is not entirely silent on this - the standard
processing archive carries a `type` column - so the honest way to support the problem
statement's premise is to measure against it rather than assert it.

FIRMS type codes:

    0  presumed vegetation fire
    1  active volcano
    2  other static land source
    3  offshore

That is four buckets, only one of which is a fire type, and none of which separates a
routine gas flare from a refinery explosion. This module quantifies the gap.

`firms_type` is never a model feature and never a source of weak labels. It exists
solely as an external yardstick; using it as an input and then scoring against it
would make the comparison circular.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

FIRMS_TYPE_LABELS: Dict[int, str] = {
    0: "presumed vegetation fire",
    1: "active volcano",
    2: "other static land source",
    3: "offshore",
}

# The coarsest statement each FIRMS type makes about a detection. Anything FIRMS
# calls a static land source or offshore is infrastructure of some kind; a presumed
# vegetation fire is not industrial. Volcanoes are natural but not vegetation.
FIRMS_TYPE_TO_AXIS: Dict[int, str] = {
    0: "NOT_INDUSTRIAL",
    1: "NOT_INDUSTRIAL",
    2: "INDUSTRIAL",
    3: "INDUSTRIAL",
}


def compare_against_firms_type(labelled: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """Quantify how much finer our classification is than the FIRMS type field.

    Returns None when `firms_type` is absent - the NRT products do not carry it, so
    this comparison is only available on archive (SP) pulls.
    """
    if "firms_type" not in labelled.columns:
        logger.info(
            "No firms_type column - NRT products omit it. "
            "Baseline comparison available only on SP archive pulls."
        )
        return None

    df = labelled[labelled["weak_label"].notna()].copy()
    df = df[pd.to_numeric(df["firms_type"], errors="coerce").notna()]
    if df.empty:
        return None

    df["firms_type"] = pd.to_numeric(df["firms_type"], errors="coerce").astype(int)

    # How many distinct answers does each system give?
    firms_counts = df["firms_type"].value_counts().to_dict()
    ours_counts = df["weak_label"].value_counts().to_dict()

    # The headline: what FIRMS lumps into "presumed vegetation fire" (type 0), split
    # by what we actually determined it to be.
    veg = df[df["firms_type"] == 0]
    veg_breakdown = veg["weak_label"].value_counts().to_dict() if not veg.empty else {}

    # Detections FIRMS calls vegetation that we identify as industrial. Each one is a
    # case the problem statement is asking to be caught.
    industrial_classes = {
        "persistent_industrial_source",
        "accidental_industrial_fire",
        "mining_or_other",
    }
    misfiled_industrial = int(
        veg["weak_label"].isin(industrial_classes).sum()
    ) if not veg.empty else 0

    # Agreement on the one axis FIRMS can express at all.
    df["firms_axis"] = df["firms_type"].map(FIRMS_TYPE_TO_AXIS)
    df["our_axis"] = np.where(
        df["weak_label"].isin(industrial_classes), "INDUSTRIAL", "NOT_INDUSTRIAL"
    )
    agree = int((df["firms_axis"] == df["our_axis"]).sum())

    report = {
        "n_compared": int(len(df)),
        "firms_type_distribution": {
            f"{k} ({FIRMS_TYPE_LABELS.get(k, 'unknown')})": int(v)
            for k, v in sorted(firms_counts.items())
        },
        "our_class_distribution": {k: int(v) for k, v in ours_counts.items()},
        "distinct_categories": {
            "firms": int(df["firms_type"].nunique()),
            "agninetra": int(df["weak_label"].nunique()),
        },
        "firms_type_0_vegetation_fire_resolved_by_us": {
            k: int(v) for k, v in veg_breakdown.items()
        },
        "industrial_detections_firms_called_vegetation": misfiled_industrial,
        "industrial_axis_agreement": round(agree / len(df), 4),
        "interpretation": (
            "FIRMS resolves this set into "
            f"{df['firms_type'].nunique()} coarse types, none of which separates "
            "routine flaring from an industrial accident. AgniNetra resolves the same "
            f"detections into {df['weak_label'].nunique()} operational classes. "
            f"{misfiled_industrial} detections FIRMS files as 'presumed vegetation "
            "fire' are identified here as industrial or mining activity."
        ),
    }

    logger.info(
        "FIRMS baseline: %d types vs our %d classes over %d detections; "
        "%d 'vegetation fires' resolved as industrial",
        report["distinct_categories"]["firms"],
        report["distinct_categories"]["agninetra"],
        report["n_compared"],
        misfiled_industrial,
    )
    return report
