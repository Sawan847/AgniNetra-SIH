"""Tests for the weak-supervision pipeline.

The behavioural tests matter more than the unit tests here. The failure this system
must never exhibit is filing a genuine industrial accident as routine flaring, so
that case is tested explicitly and against the exact mechanism that used to break it.
"""

from __future__ import annotations

import pandas as pd
import pytest

from ml.data.simulate import (
    build_facility_registry,
    expected_class_for_site_type,
    simulate_detections,
)
from ml.features.site_features import (
    SITE_FEATURE_COLUMNS,
    assign_sites,
    build_feature_frame,
    compute_site_statistics,
)
from ml.labeling.weak_labels import (
    TRAINED_CLASSES,
    apply_weak_labels,
    label_coverage_report,
)


@pytest.fixture(scope="module")
def detections() -> pd.DataFrame:
    return simulate_detections(n_days=200, random_state=7)


@pytest.fixture(scope="module")
def facilities():
    return build_facility_registry()


@pytest.fixture(scope="module")
def featured(detections, facilities) -> pd.DataFrame:
    return build_feature_frame(detections, facilities=facilities)


@pytest.fixture(scope="module")
def labelled(featured) -> pd.DataFrame:
    return apply_weak_labels(featured)


def test_simulator_emits_no_labels(detections):
    """The simulator must not leak a class into the detection record."""
    for banned in ("weak_label", "label", "fire_class", "predicted_class"):
        assert banned not in detections.columns


def test_simulator_uses_firms_schema(detections):
    required = {
        "latitude", "longitude", "bright_ti4", "bright_ti5", "scan", "track",
        "acq_date", "acq_time", "satellite", "instrument", "confidence",
        "version", "frp", "daynight",
    }
    assert required.issubset(set(detections.columns))


def test_all_feature_columns_present(featured):
    missing = [c for c in SITE_FEATURE_COLUMNS if c not in featured.columns]
    assert missing == [], f"missing engineered features: {missing}"


def test_persistence_separates_infrastructure_from_events(featured):
    """A flare must show far higher persistence than a wildfire.

    This is the single feature the whole approach rests on.
    """
    by_type = featured.groupby("site_type")["persistence_ratio"].mean()
    assert by_type["flare"] > 0.5
    assert by_type["forest"] < 0.2
    assert by_type["flare"] > by_type["forest"] * 3


def test_single_sighting_is_not_persistent():
    """One detection is no evidence of permanence.

    n_days / span_days would give 1/1 = 1.0 for a site seen exactly once, which
    would make every one-off wildfire look like a gas flare.
    """
    df = pd.DataFrame([{
        "latitude": 22.35, "longitude": 70.06, "acq_date": "2025-06-01",
        "frp": 40.0, "bright_ti4": 350.0, "bright_ti5": 320.0, "daynight": "N",
    }])
    stats = compute_site_statistics(assign_sites(df))
    assert stats["persistence_ratio"].iloc[0] == 0.0


def test_distances_are_measured_not_derived_from_landcover(featured):
    """Infrastructure distance must not be a function of land-cover class.

    Regression test for the original bug, where dist_nearest_forest and friends were
    computed as `0.2 if lc_class == 10 else ...`, making four separate spatial
    features into re-encodings of one variable.
    """
    industrial = featured[featured["land_cover_class"] == 50]
    assert industrial["dist_industrial_km"].nunique() > 5, (
        "distance takes too few distinct values for one land-cover class - "
        "it is probably derived from land cover rather than measured"
    )


def test_labels_only_from_trained_classes(labelled):
    got = set(labelled["weak_label"].dropna().unique())
    assert got.issubset(set(TRAINED_CLASSES))


def test_uncertain_is_never_a_training_label(labelled):
    """Abstention is a decision rule, not a class with a physical signature."""
    assert "uncertain" not in set(labelled["weak_label"].dropna().unique())
    assert "uncertain" not in TRAINED_CLASSES


def test_undecidable_rows_are_excluded_not_forced(labelled):
    """Rows the rules cannot resolve must stay unlabelled."""
    assert labelled["weak_label"].isna().sum() > 0
    unresolved = labelled[labelled["weak_label"].isna()]
    assert (unresolved["label_confidence"] == 0.0).all()


def test_coverage_is_reported(labelled):
    rep = label_coverage_report(labelled)
    assert 0.0 < rep["coverage"] <= 1.0
    assert rep["labelled"] + rep["unlabelled_excluded"] == rep["total_detections"]


def test_industrial_accident_is_not_filed_as_routine_flaring(labelled):
    """The failure this system exists to prevent.

    An accident at a refinery also satisfies the flare and persistence rules, because
    the site genuinely IS a persistent flare. Under summed-priority voting those two
    routine rules (70 + 60) outvoted the anomaly rule (90) and every real incident at
    a known site was filed as normal operation. Resolution is by highest authority
    precisely so this cannot happen.
    """
    incidents = labelled[labelled["is_incident"] == 1]
    assert len(incidents) > 0, "simulator produced no incidents to test"

    filed_as_routine = (incidents["weak_label"] == "persistent_industrial_source").sum()
    assert filed_as_routine == 0, (
        f"{filed_as_routine} of {len(incidents)} incident detections were filed as "
        "routine flaring - the anomaly rule is being outvoted"
    )

    caught = (incidents["weak_label"] == "accidental_industrial_fire").sum()
    assert caught == len(incidents)


def test_routine_flaring_does_not_raise_accident_labels(labelled):
    """The other side of the same coin: no alarm-spam from normal operation."""
    routine = labelled[(labelled["site_type"] == "flare") & (labelled["is_incident"] == 0)]
    false_alarms = (routine["weak_label"] == "accidental_industrial_fire").sum()
    assert false_alarms == 0


def test_weak_labels_agree_with_known_site_types(labelled):
    """Sanity check against the infrastructure the detections were placed on."""
    sub = labelled[labelled["weak_label"].notna()].copy()
    sub["expected"] = sub.apply(
        lambda r: "accidental_industrial_fire" if r["is_incident"] == 1
        else expected_class_for_site_type(r["site_type"]),
        axis=1,
    )
    agreement = (sub["weak_label"] == sub["expected"]).mean()
    assert agreement > 0.95, f"weak label agreement only {agreement:.3f}"


def test_empty_input_does_not_crash():
    empty = pd.DataFrame(columns=["latitude", "longitude", "acq_date", "frp"])
    out = apply_weak_labels(empty)
    assert len(out) == 0
    rep = label_coverage_report(out)
    assert rep["total_detections"] == 0
