# AgniNetra AI

**SIH26162 · National Technical Research Organisation (NTRO) · Theme: Disaster Management**

> AI-Based Detection and Classification of Industrial Fires and Persistent Thermal
> Sources Using NASA FIRMS, OSM & Satellite Data

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18.3+-61DAFB.svg?logo=react)](https://reactjs.org)
[![PostGIS](https://img.shields.io/badge/PostGIS-16--3.4-336791.svg?logo=postgresql)](https://postgis.net)
[![MapLibre](https://img.shields.io/badge/MapLibre_GL-4.7+-blue.svg)](https://maplibre.org)

---

## The problem, in the problem statement's own words

> *"Current satellite-based fire monitoring systems such as NASA FIRMS provide
> thermal anomaly detections but **do not distinguish** between industrial fires, gas
> flares, agricultural burning, mining activity, and wildfires."*

India's refineries, petrochemical complexes, LNG terminals, steel plants and thermal
power stations are visible from orbit every night. So are its wildfires, its coal
seam fires, and — for six weeks each autumn — most of Punjab.

NASA gives all of them to you as the same thing: a latitude, a longitude, and a
temperature.

That undifferentiated feed is useless for disaster response. An operations centre
watching for **accidental industrial fires, gas leaks and explosions** cannot act on
a list where five thousand nightly rows are refinery flares behaving exactly as
designed. The signal that matters is buried in noise that looks identical to it.

**AgniNetra reads that feed.**

---

## The two deliverables

The problem statement asks for exactly two things. Both are implemented and running.

### (i) Classification and segregation of industrial fires from natural fires

Detections are separated on the primary axis the PS names, and then refined into the
five categories it lists:

```
                    ┌── INDUSTRIAL ──┬── accidental industrial fire   (the emergency)
                    │                ├── persistent industrial source (flare, furnace, LNG boil-off)
   thermal          │                └── mining / coal seam
   detection  ──────┤
                    ├── NATURAL ────── forest / wildfire
                    │
                    └── AGRICULTURAL ─ crop residue burning
```

Agricultural burning is deliberately its own tier. It is anthropogenic, so calling it
"natural" is wrong; it is not industrial either. Collapsing it into either bucket
would inflate the headline segregation score by mislabelling roughly a sixth of all
Indian detections.

Below a calibrated confidence threshold the model **declines to classify** and routes
the detection to human verification, rather than guessing.

### (ii) GIS-based storage and map overlay

PostGIS-backed storage (PostgreSQL 16 + PostGIS 3.4 + TimescaleDB hypertable),
served through FastAPI to a React + MapLibre GL console. Every detection is a point
on the map, coloured by class, with the persistent-source registry and live alert
feed as overlays.

---

## What makes this hard, and what we actually built

### A single detection tells you almost nothing

A refinery flare and a burning field look nearly identical in one frame. What
separates them is **behaviour over time**.

Detections are clustered with haversine DBSCAN at 500 m — VIIRS I-band is 375 m, so
that is roughly one pixel of geolocation scatter — into physical **sites**. Each site
then accumulates a history:

```
persistence_ratio = active days / observed days
```

| Source | Nights burning, out of 90 |
|---|---|
| Refinery gas flare | ~85 |
| Steel / thermal power furnace | ~65 |
| LNG boil-off flaring | ~40 (episodic, tanker-driven) |
| Landfill smouldering | ~30 |
| Crop residue belt | seasonal burst, then nothing |
| Wildfire | 2 |

### The hard case: a site that burns every night *on purpose*

This is the case the PS is really about — *"accidental industrial fires, gas leaks,
explosions… risks to critical infrastructure and public safety."*

A refinery flare is not an emergency. A refinery **fire** is a disaster. Same
coordinates. Same map pixel.

So the alerting rule is never "FRP is high." It is **"FRP is high *for this site*."**

Each site's baseline uses a **median absolute deviation** scale estimator rather than
a standard deviation, because the anomaly is inside the sample: a two-day refinery
fire inflates that site's own σ enough that the fire stops clearing a 4σ bar. It
hides itself. MAD ignores the tail, so the baseline describes normal operation
instead of normal-plus-incident.

Result, on the same Jamnagar pixel:

```
routine flaring   ->  persistent_industrial_source   no alert
the incident      ->  accidental_industrial_fire     CRITICAL

  Active on 323 of 365 observed days (88% persistence)
  181 m from mapped industrial infrastructure (OSM)
  I4-I5 separation 29.2 K — sub-pixel source far hotter than a spreading fire
  FRP 945 MW against this site's own baseline of 46 MW (75 sigma above normal)
```

### Physics, not just gradient boosting

`brightness_delta` = I-4 (≈4 µm) − I-5 (≈11 µm). A small, very hot source shows a
large separation; a large cool fire front does not. This is the discriminator behind
NOAA's VIIRS Nightfire flare product, reduced to features FIRMS already gives you.

### Labels, without a labelled dataset

No labelled corpus of Indian industrial thermal sources exists, and hand-labelling a
few hundred points overfits. `ml/labeling/weak_labels.py` implements **programmatic
weak supervision**: nine labelling functions vote from evidence *external* to the
model's feature set — OSM geometry, multi-night persistence, I4/I5 thermal physics,
crop-burning seasonality, burn-scar confirmation.

Conflicts resolve by **highest authority, not summed votes**. This matters
structurally: an accident at a refinery necessarily also satisfies the flare and
persistence rules, because the site really *is* a persistent flare. Under summed
voting those two routine rules always outvoted the anomaly rule, and every genuine
incident at a known site was filed as normal operation — precisely the failure the
system exists to prevent. Incident recall went from **20/55 to 55/55** when this was
fixed.

Detections where the rules disagree are left **unlabelled and excluded**, never
forced into a class. Current coverage: **96.7%**.

---

## Honest evaluation

Two splits, because either alone misleads:

- **Spatial GroupKFold on `site_id`** — thermal detections are strongly
  autocorrelated in space. A random split puts the same refinery in train and test,
  and the model scores well by memorising a location.
- **Chronological holdout** (final 20%) — the operational task is classifying
  tomorrow from a model fitted on history.

The model is selected on cross-validation and **never** on the holdout.

Two things we report that most submissions won't:

**Label circularity.** The labelling functions key on `dist_industrial_km`,
`persistence_ratio` and `land_cover_class`, and the model sees those same features. A
near-perfect score therefore shows the model recovered the rules — not that it
classifies real fires well. `run_ablation()` retrains with those features withheld
and reports both numbers.

**Absent-class scoring.** A seasonal class with zero holdout support scores F1 = 0
and silently drags the macro average. We report macro-F1 over supported classes *and*
over all classes, and name which classes were unscored.

> **These figures come from simulated detections, where classes are separable by
> construction.** Real FIRMS data will be materially messier. The model card states
> this in `data_provenance`, and the dashboard prints it on screen. The pipeline is
> validated; the numbers await real data.

---

## Quick start

```bash
cp .env.example .env
python -m venv .venv && .venv/Scripts/activate          # Windows
pip install --only-binary=:all: -r backend/requirements.txt
```

> **Python 3.13+ note.** The pinned `pydantic==2.9.2` has no wheel for very recent
> CPython and pip will try to compile Rust. Install unpinned with
> `--only-binary=:all:` if that happens.

**Offline — no API key, works with no network:**

```bash
python scripts/build_dataset.py --source sim     # build dataset + train
python scripts/seed_from_pipeline.py --reset     # load into PostGIS/SQLite
```

**Live NASA FIRMS** — free instant key at
[firms.modaps.eosdis.nasa.gov/api/map_key](https://firms.modaps.eosdis.nasa.gov/api/map_key/),
then set `FIRMS_MAP_KEY` in `.env`:

```bash
python scripts/build_dataset.py --source firms --bbox 68.0,6.0,98.0,38.0 --start 2025-10-01 --days 60
```

Both paths run **identical** feature engineering, labelling and training code. Only
the input rows differ.

**Run the stack:**

```bash
docker compose up -d
```

Frontend `:5173` · API docs `:8000/docs`

---

## Architecture

```
NASA FIRMS  (VIIRS SNPP / NOAA-20 / NOAA-21 · MODIS)  ─┐
OpenStreetMap Overpass (industrial · quarry · landfill) ┼─> ingestion
ESA WorldCover land cover                              ─┘        │
                                                                 v
                                    DBSCAN 500 m site clustering
                                               │
                       site persistence · FRP baselines (MAD robust scale)
                       real BallTree distances to OSM geometry
                       I4-I5 thermal separation
                                               │
                       weak supervision (9 LFs, highest-authority resolution)
                                               │
                     spatial GroupKFold + chronological holdout + ablation
                                               │
                      classifier + abstention -> human verification queue
                                               │
                      FastAPI  ->  React + MapLibre  ->  alerts
```

| Path | Role |
|---|---|
| `ml/labeling/weak_labels.py` | Labelling functions, superclass axis, vote resolution |
| `ml/features/site_features.py` | Site clustering, persistence, real OSM distances |
| `ml/training/train_pipeline.py` | Training, spatial CV, ablation, model card |
| `ml/data/simulate.py` | Offline detection simulator (FIRMS schema, **no labels**) |
| `backend/app/services/firms.py` | NASA FIRMS Area API client |
| `backend/app/services/osm.py` | Overpass infrastructure client |
| `backend/app/services/classifier.py` | Inference with evidence generation |
| `scripts/build_dataset.py` | End-to-end dataset build and training |

### Facility coverage

Every facility class the PS names is represented in the demo registry: **oil
refineries** (Jamnagar, Koyali, Panipat), **petrochemical complexes** (Haldia,
Dahej), **LNG terminals** (Dahej, Hazira, Kochi), **steel industries** (Bhilai,
Rourkela, Tata Jamshedpur), **thermal power** (Korba, Singrauli), **mining areas**
(Jharia, Talcher) — plus landfills, crop belts and forest reserves as the
counter-classes.

---

## Design decisions worth defending

**Abstention is a decision rule, not a class.** There is no physically "uncertain"
fire. Below threshold the model declines and routes to human review. Training a sixth
`uncertain` category asks the model to learn a signature that does not exist.

**Unavailable data returns `null`, never a plausible value.** When Google Earth
Engine is unconfigured, `gee.py` reports `imagery_available: false`. It previously
returned NDVI and ΔNBR drawn from random distributions, tagged as available, which
surfaced in the UI as evidence on operational alerts. A fabricated spectral index on
a fire alert is worse than none: nothing downstream can distinguish it from a real
one.

**One feature-engineering entry point.** Training and inference both call
`build_feature_frame()`, so a feature cannot be computed one way in training and
another in production.

**O(n log n), not O(n²).** Distance queries use a BallTree. India yields 10k–50k
VIIRS detections per day; a per-row Python loop over a 90-day window does not finish.

---

## Known limitations

- **This is not a fire alarm.** FIRMS runs ~3 h behind with 4–8 passes a day. On-site
  sensors will always win on speed. The value is *independence and coverage* — a
  facility can decline to report an incident; it cannot decline to be overflown.
- **Cloud blocks observation**, and monsoon gaps are not random with respect to
  burning behaviour.
- **Co-located units cannot be resolved.** Where several facilities share a 375 m
  pixel, the honest output is a ranked candidate set.
- Weak labels are noisy; a manually verified test set is required before any
  real-world accuracy claim.
- `burn_scar_within_30d` needs a MODIS MCD64A1 join; without it the
  highest-precision labelling function never fires.

---

## Roadmap

- MCD64A1 burned-area join to activate the burn-scar labelling function
- Sentinel-5P NO₂/SO₂ co-location as an independent industrial-combustion signature
- Brick-kiln detection from Sentinel-2 SWIR (distinctive oval footprint)
- New-source detection: a persistent site appearing where no facility is mapped
- District-wise PDF reporting for state disaster management authorities

---

## License

Smart India Hackathon open-source project.
