# AgniNetra AI — System Architecture & Design

## 1. Overview

**AgniNetra AI** is a production-grade geospatial intelligence and AI-enabled thermal classification platform designed for the Smart India Hackathon. It integrates satellite thermal anomalies (NASA FIRMS), OpenStreetMap industrial infrastructure vectors, ESA WorldCover land-classification data, and Sentinel-2 satellite imagery to classify thermal anomalies into six distinct categories:

1. **Accidental Industrial Fire** (High Risk / Disaster Response)
2. **Persistent Industrial Thermal Source / Gas Flare** (Refineries, Steel Plants, Flares)
3. **Forest / Natural Fire** (Wildfires, National Parks, Bio-reserves)
4. **Agricultural Burning** (Crop stubble residue, seasonal farming)
5. **Mining / Other Thermal Activity** (Open-cast coal mines, slag heaps)
6. **Uncertain** (Mixed spectral signatures, low confidence, cloud interference)

---

## 2. High-Level System Architecture

```
+-----------------------------------------------------------------------+
|                            CLIENT LAYER                               |
|   React 18 + TypeScript + Vite + MapLibre GL JS + Recharts            |
+-----------------------------------------------------------------------+
                                  |
                           REST / GeoJSON
                                  v
+-----------------------------------------------------------------------+
|                            BACKEND API                                |
|   FastAPI Gateway (CORS, Request Logging, Error Handling)            |
|   - /api/v1/health          - /api/v1/hotspots                        |
|   - /api/v1/predictions     - /api/v1/alerts                          |
|   - /api/v1/analytics       - /api/v1/models                          |
+-----------------------------------------------------------------------+
            |                             |                   |
            v                             v                   v
+-----------------------+     +--------------------+   +----------------+
|      DATA LAYER       |     | FEATURE ENGINE     |   |  ML PIPELINE   |
| PostgreSQL 16+PostGIS |     | PostGIS Spatial    |   | XGBoost Model  |
| 11 Tables (SRID 4326) |<--->| Proximity, Density |-->| Multi-Class    |
| Spatial GIST Indexes  |     | & Persistence Calc |   | Probabilities  |
+-----------------------+     +--------------------+   +----------------+
            ^
            | (Ingestion workers)
+-----------------------------------------------------------------------+
|                          EXTERNAL SOURCES                             |
|  NASA FIRMS (VIIRS/MODIS) | OpenStreetMap Overpass | ESA WorldCover   |
+-----------------------------------------------------------------------+
```

---

## 3. Database Schema (PostGIS SRID 4326)

The database consists of **11 primary tables** with spatial indexing:

| Table | Geometry Column | Description |
|---|---|---|
| `hotspots` | `geom` (Point) | Satellite thermal detections from NASA FIRMS |
| `industrial_facilities` | `location` (Point), `footprint` (Polygon) | Known factories, refineries, power plants |
| `land_cover` | `geom` (Polygon) | ESA WorldCover 10m land classification polygons |
| `hotspot_features` | — | Engineered spatial, temporal, and context features |
| `predictions` | — | Multi-class model inference outputs with probabilities |
| `alerts` | — | Operational alerts with severity and lifecycle statuses |
| `analyst_feedback` | — | Human-in-the-loop analyst confirmations/corrections |
| `users` | — | Role-based platform authentication (admin, analyst, viewer) |
| `model_versions` | — | Model lineage, versioning, parameters, and metric tracking |
| `ingestion_runs` | — | Operational ingestion logs and data counts |
| `audit_logs` | — | Immutable audit trail of system/user actions |

---

## 4. Machine Learning Classification Pipeline

### Feature Vectors (16 core dimensions)
- **Thermal**: `brightness`, `bright_ti4`, `bright_ti5`, `frp` (Fire Radiative Power), `confidence`
- **Spatial Proximity**: `dist_nearest_facility`, `dist_nearest_road`, `dist_nearest_forest`
- **Temporal & Density**: `nearby_hotspot_count_24h`, `nearby_hotspot_count_7d`, `persistence_score`
- **Environmental Context**: `land_cover_class`, `ndvi_value`, `lst_delta`, `is_nighttime`, `day_of_year`

### Model Strategy
- Primary: **XGBoost Multi-Class Softmax Classifier** (`objective: multi:softprob`)
- Fallback: **scikit-learn Random Forest Classifier**
- Outputs: Normalized probability vector across all 6 classes, top predicted label, confidence score, and top feature attribution.

---

## 5. Security Architecture
- Parameterized SQL queries via SQLAlchemy ORM (SQL injection prevention)
- Strict CORS validation for authorized frontend origins
- Password hashing using bcrypt
- Structured, sanitized logging without credential exposure
- Isolated Docker networking with health checks
