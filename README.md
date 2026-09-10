# AgniNetra AI — Industrial Thermal Intelligence and Fire Classification Platform

[![Smart India Hackathon](https://img.shields.io/badge/SIH-2024-orange.svg)](https://sih.gov.in)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18.3+-61DAFB.svg?logo=react)](https://reactjs.org)
[![PostGIS](https://img.shields.io/badge/PostGIS-16--3.4-336791.svg?logo=postgresql)](https://postgis.net)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.5+-3178C6.svg?logo=typescript)](https://www.typescriptlang.org)
[![MapLibre](https://img.shields.io/badge/MapLibre_GL-4.7+-blue.svg)](https://maplibre.org)

**AgniNetra AI** is a production-grade geospatial intelligence platform that integrates **NASA FIRMS** satellite thermal anomaly detections, **OpenStreetMap** industrial infrastructure vectors, **ESA WorldCover** land-use classification, and **Sentinel-2** satellite imagery. 

The platform employs spatial feature engineering and machine learning (XGBoost/Random Forest) to accurately classify thermal events into 6 distinct categories:

1. **Accidental Industrial Fire** (Refineries, chemical plants, factories)
2. **Persistent Industrial Thermal Source / Gas Flare** (Refinery flares, blast furnaces)
3. **Forest / Natural Fire** (Wildfires, biosphere reserves)
4. **Agricultural Burning** (Stubble residue burning, seasonal clearing)
5. **Mining / Other Thermal Activity** (Open-cast mining, coal seams, slag)
6. **Uncertain** (Low-confidence / obscured signatures)

---

## 🏗️ Repository Architecture

```
AgniNetra-SIH/
├── backend/                # FastAPI application & database models
│   ├── alembic/            # Database migrations
│   ├── app/
│   │   ├── api/v1/         # Health, Hotspots, Predictions endpoints
│   │   ├── middleware/     # CORS, structured access logs, error handlers
│   │   ├── models/         # 11 PostGIS / SQLAlchemy ORM models
│   │   ├── schemas/        # Pydantic request / response validation
│   │   ├── utils/          # Structured logging
│   │   ├── config.py       # Pydantic Settings
│   │   ├── database.py     # Database session management
│   │   └── main.py         # FastAPI app factory
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── requirements.txt
├── frontend/               # React 18 + TypeScript + Vite application
│   ├── src/
│   │   ├── api/            # API client wrapper
│   │   ├── components/     # AppShell, Sidebar, Header, HealthIndicator, MapView
│   │   ├── hooks/          # useHealthCheck polling hook
│   │   ├── pages/          # Dashboard, Map, Analytics, Settings
│   │   ├── styles/         # Dark-themed responsive design
│   │   ├── types/          # TypeScript definitions & classifications
│   │   ├── App.tsx         # React Router v6 setup
│   │   └── main.tsx
│   ├── Dockerfile
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── ml/                     # Machine Learning Pipeline
│   ├── features/           # Persistence, proximity & day-of-year calculations
│   ├── models/             # XGBoost/Random Forest multi-class classifier
│   ├── training/           # Train/test splitting & synthetic data pipeline
│   ├── evaluation/         # F1, precision, recall & confusion matrix metrics
│   └── config.py
├── scripts/
│   ├── setup_dev.ps1       # Windows PowerShell automated setup
│   └── seed_demo.py        # Clearly marked demonstration fixtures seeder
├── tests/
│   ├── backend/            # Pytest tests for API, DB & Config
│   ├── frontend/           # Vitest tests for React components & pages
│   └── ml/                 # Tests for ML features, models & metrics
├── docs/                   # System architecture & API documentation
├── infra/                  # Docker initialization & PostGIS scripts
├── docker-compose.yml      # Orchestrates PostGIS, Backend & Frontend
├── .env.example            # Configuration template (no secrets)
└── .gitignore
```

---

## 🚀 Quick Start Guide

### Prerequisites
- **Python 3.11+**
- **Node.js 18+** & **npm**
- **Docker Desktop** (for PostgreSQL + PostGIS)

---

### Method 1: Docker Compose (Full Stack)

```bash
# 1. Clone & enter repository
git clone https://github.com/your-org/AgniNetra-SIH.git
cd AgniNetra-SIH

# 2. Setup environment file
cp .env.example .env

# 3. Start PostgreSQL/PostGIS, Backend & Frontend
docker compose up -d

# 4. Access services:
# Frontend:  http://localhost:5173
# Backend:   http://localhost:8000/docs
# Health:    http://localhost:8000/api/v1/health
```

---

### Method 2: Local Development Setup (Windows PowerShell)

#### Step 1: Automated Script
```powershell
.\scripts\setup_dev.ps1
```

#### Step 2: Manual Step-by-Step

**1. Start PostGIS Database:**
```powershell
docker compose up -d db
```

**2. Backend Setup:**
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
python ..\scripts\seed_demo.py
uvicorn app.main:app --reload --port 8000
```

**3. Frontend Setup:**
```powershell
cd frontend
npm install
npm run dev
```

---

## 🧪 Running Tests

### Backend & ML Tests (Pytest)
```powershell
cd backend
pytest ../tests/backend/ ../tests/ml/ -v
```

### Frontend Tests (Vitest)
```powershell
cd frontend
npm run test
```

### Frontend Type Checking & Build
```powershell
cd frontend
npm run typecheck
npm run build
```

---

## 📊 Database Entities (11 PostGIS Tables)

1. `hotspots` — Thermal anomaly detections (Point geom SRID 4326, FRP, brightness, sensor metadata)
2. `industrial_facilities` — Factories, refineries, power plants (Point location, Polygon footprint)
3. `land_cover` — ESA WorldCover classifications (Polygon geom)
4. `hotspot_features` — Proximity to infrastructure, persistence scores, temporal features
5. `predictions` — ML classification results and 6-class probability distribution
6. `alerts` — Operational incident alerts (critical, high, medium, low severity)
7. `analyst_feedback` — Human-in-the-loop analyst feedback and corrections
8. `users` — Role-based access (admin, analyst, viewer)
9. `model_versions` — Machine learning model registry, hyperparameters, and evaluation metrics
10. `ingestion_runs` — FIRMS/OSM ingestion runs and data audit logs
11. `audit_logs` — Immutable audit log of all system actions

---

## 🔒 Security & Best Practices
- **No Hardcoded Credentials**: Configured via environment variables with `.env.example` template.
- **SQL Injection Prevention**: SQLAlchemy parameterized ORM queries.
- **CORS Protection**: Restricted to configured frontend origins.
- **Structured Logging**: Timestamps, levels, module tracking, and exception stack traces.
- **Demonstration Isolation**: All demo data is strictly labeled and isolated in `scripts/seed_demo.py`.

---

## 📜 License
Smart India Hackathon (SIH) Open Source Project.
