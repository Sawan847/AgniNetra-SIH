# AgniNetra AI

**SIH26162 — AI-Based Detection and Classification of Industrial Fires and Persistent Thermal Sources Using NASA FIRMS, OSM & Satellite Data**

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18.3+-61DAFB.svg?logo=react)](https://reactjs.org)
[![PostGIS](https://img.shields.io/badge/PostGIS-16--3.4-336791.svg?logo=postgresql)](https://postgis.net)
[![MapLibre](https://img.shields.io/badge/MapLibre_GL-4.7+-blue.svg)](https://maplibre.org)

---

## The problem, stated precisely

NASA FIRMS does not detect fires. It detects **thermal anomalies** — and in an
industrialised Indian landscape most of them are not wildfires at all:

| Source | Why FIRMS flags it |
|---|---|
| Refinery gas flares | Burns every night for years at ~1600–2000 K |
| Steel, coke, cement furnaces | Continuous industrial heat |
| Brick kilns | Seasonal, Oct–Jun, clustered across the Indo-Gangetic plain |
| Landfill fires | Ghazipur, Deonar, Bhalswa — recurrent smouldering |
| Crop residue burning | Punjab/Haryana, Oct–Nov and Apr–May |
| Actual wildfires | Transient, spreading, leaves a burn scar |

So "plot the FIRMS feed on a map" solves nothing. **The problem is separating
permanent infrastructure from genuine events — and, at a site that burns every
single night, detecting the one night it burns wrong.**

That second half is the operational crux. A refinery flare is not an emergency. A
refinery *fire* is. Both occupy the same pixel.

---

## How AgniNetra answers it

### 1. Classify sites, not pixels

A single detection carries almost no information — a flare and a burning field look
nearly identical in one frame. What separates them is **behaviour over time**.

Detections are clustered with haversine DBSCAN at 500 m (VIIRS I-band is 375 m, so
one pixel of geolocation scatter) into physical **sites**. Each site then gets
temporal statistics: persistence ratio, FRP variability, centroid drift, night
fraction.

```
persistence_ratio = active days / observed days
```

A gas flare approaches 1.0. A wildfire is a single day.

### 2. Anomaly against a site's own baseline

The alerting rule is not "FRP is high." It is **"FRP is high *for this site*."**

Each site's baseline uses a **median absolute deviation** scale estimator, not a
standard deviation — because the anomaly is inside the sample. A two-day refinery
fire inflates that site's own σ enough that the fire stops clearing a 4σ bar. MAD
ignores the tail, so the baseline describes normal operation instead of
normal-plus-incident.

Result, on the same Jamnagar pixel:

```
routine flaring  -> persistent_industrial_source   (no alert, 481/481)
the incident     -> accidental_industrial_fire     (alert,    16/16)

  evidence: Active on 323 of 365 observed days (88% persistence)
            181 m from mapped industrial infrastructure (OSM)
            I4-I5 separation 29.2 K - sub-pixel source far hotter
              than a spreading vegetation fire
            FRP 945 MW against this site's own baseline of 46 MW
              (75 sigma above normal operation)
```

### 3. Labels without a labelled dataset

No labelled corpus of Indian industrial thermal sources exists. Rather than
hand-label a few hundred points and overfit, AgniNetra uses **programmatic weak
supervision** (`ml/labeling/weak_labels.py`): nine labelling functions vote from
evidence *external* to the model — OSM geometry, multi-night persistence, I4/I5
thermal physics, burn-scar confirmation, crop-burning seasonality.

Conflicts resolve by **highest authority, not summed votes**. This matters
structurally: an accident at a refinery necessarily *also* satisfies the flare and
persistence rules, because the site really is a persistent flare. Under summed
voting those two routine rules always outvote the anomaly rule, and every genuine
incident at a known site gets filed as normal operation — precisely the failure the
system exists to prevent.

Detections where the rules disagree are left **unlabelled and excluded**, never
forced into a class.

### 4. Physics, not just gradient boosting

`brightness_delta` = I-4 (4 µm) − I-5 (11 µm). A small, very hot source shows a
large separation; a large cool fire front does not. This is the discriminator behind
NOAA's VIIRS Nightfire flare product, reduced to features FIRMS actually gives you.

---

## Honest evaluation

Two splits, because either alone misleads:

- **Spatial GroupKFold on site_id** — thermal detections are strongly
  autocorrelated in space. A random split puts the same refinery in train and test,
  and the model scores well by memorising a location.
- **Chronological holdout** — the real task is classifying tomorrow from a model fit
  on history.

The model is selected on CV, never on the holdout.

**A caveat we state up front rather than bury.** The labelling functions key on
`dist_industrial_km`, `persistence_ratio` and `land_cover_class`, and those same
features feed the model. A near-perfect score therefore shows the model recovered
the rules — not that it classifies real fires well. `run_ablation()` retrains with
those features withheld and reports both numbers. On the offline dataset:

```
all features                    macro-F1  1.000
rule-defining features withheld macro-F1  0.998
```

The remaining thermal and FRP-dynamics features carry the classification
independently. **But these figures come from simulated detections where classes are
separable by construction — real FIRMS data will be materially messier.** Every
model card carries this note, the label-coverage breakdown, and a list of known
limitations.

---

## Quick start

```bash
cp .env.example .env
python -m venv .venv && .venv/Scripts/activate    # Windows
pip install -r backend/requirements.txt
```

**Offline (no API key, works on a demo booth with no wifi):**

```bash
python scripts/build_dataset.py --source sim
```

**Live NASA FIRMS** — free instant key at
[firms.modaps.eosdis.nasa.gov/api/map_key](https://firms.modaps.eosdis.nasa.gov/api/map_key/),
then put it in `.env` as `FIRMS_MAP_KEY`:

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
NASA FIRMS (VIIRS SNPP / NOAA-20 / NOAA-21)  ─┐
OpenStreetMap Overpass (industrial/mine/landfill) ─┼─> ingestion
ESA WorldCover land cover                     ─┘        │
                                                        v
                           DBSCAN 500 m site clustering
                                      │
                      site persistence · FRP baselines (MAD)
                      real BallTree distances to OSM geometry
                      I4-I5 thermal separation
                                      │
                      weak supervision (9 LFs, max-authority)
                                      │
                    spatial GroupKFold + chronological holdout
                                      │
                     classifier + abstention -> review queue
                                      │
                     FastAPI  ->  React + MapLibre  ->  alerts
```

| Path | Role |
|---|---|
| `ml/labeling/weak_labels.py` | Labelling functions and vote resolution |
| `ml/features/site_features.py` | Site clustering, persistence, real OSM distances |
| `ml/training/train_pipeline.py` | Training, spatial CV, ablation, model card |
| `ml/data/simulate.py` | Offline detection simulator (FIRMS schema, no labels) |
| `backend/app/services/firms.py` | NASA FIRMS Area API client |
| `backend/app/services/osm.py` | Overpass infrastructure client |
| `backend/app/services/classifier.py` | Inference with evidence generation |
| `scripts/build_dataset.py` | End-to-end dataset build and training |

---

## Design decisions worth defending

**Abstention is a decision rule, not a class.** There is no physically "uncertain"
fire. Below a confidence threshold the model declines and routes the detection to a
human verification queue. Training a sixth `uncertain` category — as an earlier
version did — asks the model to learn a signature that does not exist, and drags
macro-F1 down for no reason.

**Unavailable data returns `null`, never a plausible value.** When Google Earth
Engine is unconfigured, `gee.py` reports `imagery_available: false`. It previously
returned NDVI and dNBR drawn from random distributions, tagged as available, which
then surfaced in the UI as evidence on operational alerts. A fabricated spectral
index on a fire alert is worse than none: nothing downstream can distinguish it from
a real one.

**One feature-engineering entry point.** Training and inference both call
`build_feature_frame()`, so a feature cannot be computed one way in training and
another in production.

**O(n log n), not O(n²).** Distance queries use a BallTree. India yields
10k–50k VIIRS detections per day; a per-row Python loop over a 90-day window does
not finish.

---

## Limitations

- Weak labels are noisy. Reported metrics measure agreement with the labelling
  functions and inherit their biases. A manually verified test set is required
  before claiming real-world accuracy.
- The offline simulator is for demos and CI. It is not real observations, and the
  model card says so in `data_provenance`.
- `burn_scar_within_30d` needs a MODIS MCD64A1 join; without it the
  highest-precision labelling function never fires.
- Sentinel-2 spectral indices require GEE credentials and are excluded rather than
  imputed when absent.

---

## Roadmap

- MCD64A1 burned-area join to activate the burn-scar labelling function
- Brick-kiln detection from Sentinel-2 SWIR (distinctive oval footprint)
- New-source detection: a persistent site appearing where none existed — unregistered
  kilns, unpermitted flaring
- Sentinel-5P NO₂/SO₂ co-location as an independent industrial signature
- District-wise PDF reporting for State Pollution Control Boards

---

## License

Smart India Hackathon open-source project.
