"""AgniNetra AI - Programmatic weak supervision for thermal anomaly labelling.

No hand-labelled dataset exists for Indian industrial thermal sources, and manually
labelling enough VIIRS detections to train a classifier is not feasible. Instead this
module derives *noisy but independent* labels from evidence external to the model's
own feature set:

  * OpenStreetMap infrastructure geometry (refineries, works, power plants, quarries)
  * Multi-night temporal persistence of the detection site itself
  * Physical thermal signature (I-4 / I-5 brightness separation, FRP magnitude)
  * Land-cover class and agricultural burning seasonality

Each labelling function (LF) votes for one class or ABSTAINs. Votes are resolved by
priority-weighted majority. Sites where the LFs disagree, or where no LF fires, are
left UNLABELLED and excluded from training - they are not forced into a class.

This is the standard Snorkel-style weak supervision pattern. The labels are noisy;
that is expected. Evaluation must be done against a held-out set of manually
verified sites, never against these labels.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

ABSTAIN = None

# Trained classes. "uncertain" is deliberately NOT here: abstention is a decision
# rule applied at inference time, not a physical category with its own signature.
TRAINED_CLASSES: List[str] = [
    "persistent_industrial_source",
    "accidental_industrial_fire",
    "forest_or_natural_fire",
    "agricultural_burning",
    "mining_or_other",
]

# ESA WorldCover class codes
LC_TREE = 10
LC_SHRUB = 20
LC_GRASS = 30
LC_CROP = 40
LC_BUILT = 50
LC_BARE = 60


# --------------------------------------------------------------------------
# Labelling functions. Each takes a row and returns a class or ABSTAIN.
# --------------------------------------------------------------------------

def lf_persistent_near_industry(r: pd.Series) -> Optional[str]:
    """A site that burns on most observed nights and sits on industrial land is
    infrastructure (gas flare, furnace, kiln), not an event."""
    if r.get("dist_industrial_km", 99.0) <= 1.0 and r.get("persistence_ratio", 0.0) >= 0.40:
        return "persistent_industrial_source"
    return ABSTAIN


def lf_flare_thermal_signature(r: pd.Series) -> Optional[str]:
    """Gas flares are small, very hot, nocturnal and spatially pinned.

    High I-4 brightness with a large I-4 minus I-5 separation indicates a sub-pixel
    source far hotter than a spreading vegetation fire. Combined with a stationary
    centroid this is the flare signature underpinning VIIRS Nightfire.
    """
    if (
        r.get("is_nighttime", 0) == 1
        and r.get("bright_ti4", 0.0) >= 350.0
        and r.get("brightness_delta", 0.0) >= 25.0
        and r.get("persistence_ratio", 0.0) >= 0.30
        and r.get("centroid_drift_km", 99.0) <= 0.5
    ):
        return "persistent_industrial_source"
    return ABSTAIN


def lf_frp_anomaly_at_known_site(r: pd.Series) -> Optional[str]:
    """An established industrial site radiating far above its own historical
    baseline is an incident, not routine operation.

    This is the discriminator that keeps routine flaring from generating alerts
    while still catching a genuine plant fire.
    """
    baseline = r.get("site_frp_median", 0.0)
    sigma = r.get("site_frp_sigma_robust", 0.0)
    if (
        r.get("dist_industrial_km", 99.0) <= 1.0
        and r.get("persistence_ratio", 0.0) >= 0.20
        and baseline > 0.0
        and sigma > 0.0
        and r.get("frp", 0.0) > baseline + 4.0 * sigma
        and r.get("frp", 0.0) > 100.0
    ):
        return "accidental_industrial_fire"
    return ABSTAIN


def lf_industrial_transient_high_frp(r: pd.Series) -> Optional[str]:
    """A large transient thermal event inside industrial land with no persistence
    history is an accident at a site that does not normally burn."""
    if (
        r.get("dist_industrial_km", 99.0) <= 0.5
        and r.get("persistence_ratio", 1.0) <= 0.10
        and r.get("frp", 0.0) >= 150.0
    ):
        return "accidental_industrial_fire"
    return ABSTAIN


def lf_forest_burn_scar(r: pd.Series) -> Optional[str]:
    """Ground-truth anchor: a detection followed by a burned-area scar is a
    confirmed vegetation fire.

    MODIS MCD64A1 maps burned area independently of the active-fire product, so a
    scar appearing at the site within ~30 days is strong, physically independent
    evidence. Highest-precision LF available.
    """
    if r.get("burn_scar_within_30d", 0) == 1 and r.get("dist_industrial_km", 99.0) > 2.0:
        return "forest_or_natural_fire"
    return ABSTAIN


def lf_landfill_persistent(r: pd.Series) -> Optional[str]:
    """Landfill smouldering: recurrent low-intensity heat on waste-disposal land.

    Ghazipur, Deonar and Bhalswa smoulder intermittently rather than nightly, so the
    persistence bar is lower than for a flare. These are persistent anthropogenic
    thermal sources - the second half of what this problem statement asks us to find.
    """
    if r.get("dist_landfill_km", 99.0) <= 1.0 and r.get("persistence_ratio", 0.0) >= 0.15:
        return "persistent_industrial_source"
    return ABSTAIN


def lf_forest_landcover_transient(r: pd.Series) -> Optional[str]:
    """A transient fire in tree or shrub cover, far from any industry.

    Note there is no spatial-spread condition. A wildfire spreads over kilometres,
    but 500 m site clustering deliberately splits it into several adjacent sites so
    that flares stay individually resolved. Each fragment is therefore small and
    transient - and transience is the discriminator that matters here.
    """
    if (
        r.get("land_cover_class", 0) in (LC_TREE, LC_SHRUB)
        and r.get("dist_industrial_km", 0.0) > 5.0
        and r.get("persistence_ratio", 1.0) <= 0.15
    ):
        return "forest_or_natural_fire"
    return ABSTAIN


def lf_crop_residue_season(r: pd.Series) -> Optional[str]:
    """Crop residue burning: cropland, in-season, daytime, low FRP.

    North-west India burns paddy residue in Oct-Nov and wheat residue in Apr-May.

    Persistence is deliberately NOT constrained. An individual field burns once, but
    a burning *belt* lights up repeatedly for six weeks, so a cropland site can show
    a high persistence ratio while being nothing like a flare. What separates the two
    is that stubble burning happens in daylight, radiates weakly, and stops dead
    outside the harvest window.
    """
    doy = r.get("day_of_year", 0)
    in_kharif = 274 <= doy <= 334      # 1 Oct - 30 Nov
    in_rabi = 105 <= doy <= 152        # 15 Apr - 31 May
    if (
        r.get("land_cover_class", 0) == LC_CROP
        and (in_kharif or in_rabi)
        and r.get("is_nighttime", 1) == 0
        and r.get("frp", 999.0) <= 60.0
        and r.get("dist_industrial_km", 0.0) > 2.0
    ):
        return "agricultural_burning"
    return ABSTAIN


def lf_mine_proximity(r: pd.Series) -> Optional[str]:
    """Quarry, opencast mine or coal seam fire."""
    if r.get("dist_mine_km", 99.0) <= 1.0 and r.get("dist_industrial_km", 99.0) > 1.0:
        return "mining_or_other"
    return ABSTAIN


# Priority resolves genuine conflicts; higher wins. Rationale: the burn-scar anchor
# is independent physical evidence and outranks everything. An FRP anomaly at a
# known site outranks the persistence rule that would otherwise call the same pixel
# routine - that is exactly the accident case we must not suppress.
LABELING_FUNCTIONS = [
    (lf_forest_burn_scar, 100),
    (lf_frp_anomaly_at_known_site, 90),
    (lf_industrial_transient_high_frp, 80),
    (lf_flare_thermal_signature, 70),
    (lf_persistent_near_industry, 60),
    (lf_landfill_persistent, 55),
    (lf_mine_proximity, 50),
    (lf_crop_residue_season, 40),
    (lf_forest_landcover_transient, 30),
]


def apply_weak_labels(df: pd.DataFrame, min_votes: int = 1) -> pd.DataFrame:
    """Apply all labelling functions and resolve votes.

    Adds four columns:
      weak_label        - resolved class, or None where the LFs could not decide
      label_confidence  - agreement fraction among the LFs that fired
      lf_votes          - the individual LF votes, for auditing
      n_lf_fired        - how many LFs produced a non-abstain vote

    Rows with weak_label None are UNLABELLED and must be excluded from training.
    """
    if df.empty:
        return df.assign(weak_label=None, label_confidence=0.0, lf_votes="", n_lf_fired=0)

    labels: List[Optional[str]] = []
    confidences: List[float] = []
    vote_logs: List[str] = []
    n_fired: List[int] = []

    for _, row in df.iterrows():
        # votes[cls]      = highest priority of any LF voting for cls (authority)
        # vote_mass[cls]  = summed priority of every LF voting for cls (corroboration)
        votes: Dict[str, int] = {}
        vote_mass: Dict[str, int] = {}
        fired: List[str] = []

        for fn, priority in LABELING_FUNCTIONS:
            try:
                vote = fn(row)
            except Exception as exc:  # a malformed row must not kill the batch
                logger.debug("LF %s failed: %s", fn.__name__, exc)
                vote = ABSTAIN
            if vote is not ABSTAIN:
                votes[vote] = max(votes.get(vote, 0), priority)
                vote_mass[vote] = vote_mass.get(vote, 0) + priority
                fired.append(fn.__name__ + "->" + vote)

        if not votes or len(fired) < min_votes:
            labels.append(None)
            confidences.append(0.0)
            vote_logs.append("|".join(fired))
            n_fired.append(len(fired))
            continue

        # Resolve by HIGHEST-AUTHORITY evidence, not by summed votes.
        #
        # Summing is wrong here, and structurally so. An accident at a refinery
        # necessarily also satisfies the flare and persistence rules - the site
        # really is a persistent flare, and it really is burning abnormally. Under
        # summed voting those two routine rules (70 + 60) always outvote the anomaly
        # rule (90), so every genuine incident at a known site gets filed as normal
        # operation. That is precisely the failure this system exists to prevent.
        #
        # Taking the maximum instead means the most specific and most authoritative
        # observation decides, and weaker corroborating rules cannot drown it out.
        # Summed weight is used only to break ties within one authority tier.
        best_priority = max(votes.values())
        contenders = [cls for cls, pr in votes.items() if pr == best_priority]
        if len(contenders) == 1:
            best = contenders[0]
        else:
            best = max(contenders, key=lambda c: vote_mass.get(c, 0))

        total_mass = sum(vote_mass.values()) or 1
        labels.append(best)
        confidences.append(round(vote_mass[best] / total_mass, 3))
        vote_logs.append("|".join(fired))
        n_fired.append(len(fired))

    out = df.copy()
    out["weak_label"] = labels
    out["label_confidence"] = confidences
    out["lf_votes"] = vote_logs
    out["n_lf_fired"] = n_fired
    return out


def label_coverage_report(df: pd.DataFrame) -> Dict[str, Any]:
    """Summarise labelling coverage and class balance for the model card."""
    if df.empty or "weak_label" not in df.columns:
        return {"total_detections": 0, "labelled": 0, "coverage": 0.0, "class_counts": {}}

    total = len(df)
    labelled_mask = df["weak_label"].notna()
    labelled = int(labelled_mask.sum())
    counts = df.loc[labelled_mask, "weak_label"].value_counts().to_dict()

    return {
        "total_detections": total,
        "labelled": labelled,
        "unlabelled_excluded": total - labelled,
        "coverage": round(labelled / total, 4) if total else 0.0,
        "class_counts": {k: int(v) for k, v in counts.items()},
        "mean_label_confidence": round(float(df.loc[labelled_mask, "label_confidence"].mean()), 4)
        if labelled
        else 0.0,
    }
