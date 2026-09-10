# AgniNetra AI — API Specification

Base URL: `http://localhost:8000/api/v1`

---

## 1. System Endpoints

### `GET /health`
Returns system health status and database latency.

**Response `200 OK`**:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "environment": "development",
  "timestamp": "2024-09-10T14:30:00Z",
  "services": [
    {
      "name": "postgresql",
      "status": "healthy",
      "latency_ms": 1.45,
      "error": null
    }
  ]
}
```

### `GET /health/ready`
Kubernetes/Docker readiness probe.

**Response `200 OK`**:
```json
{
  "ready": true
}
```

---

## 2. Hotspots Endpoints

### `GET /hotspots`
Query paginated hotspot records.

**Query Parameters**:
- `page` (int, default: 1): Page number (>= 1)
- `per_page` (int, default: 50): Number of records (1..200)

**Response `200 OK`**:
```json
{
  "status": "success",
  "data": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "latitude": 22.472,
      "longitude": 69.873,
      "brightness": 395.4,
      "bright_ti4": 401.2,
      "bright_ti5": 382.1,
      "frp": 320.5,
      "confidence": 95.0,
      "satellite": "SNPP",
      "instrument": "VIIRS",
      "acq_date": "2024-09-10",
      "acq_time": "14:30:00",
      "daynight": "N",
      "source": "FIRMS",
      "ingested_at": "2024-09-10T14:35:00Z"
    }
  ],
  "meta": {
    "total": 1,
    "page": 1,
    "per_page": 50
  }
}
```

### `GET /hotspots/{hotspot_id}`
Retrieve a single hotspot record by UUID.

**Response `200 OK`**:
```json
{
  "status": "success",
  "data": { ... }
}
```

**Response `404 Not Found`**:
```json
{
  "status": "error",
  "error": {
    "code": "NOT_FOUND",
    "message": "Hotspot not found"
  }
}
```
