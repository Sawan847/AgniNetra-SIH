"""Integration tests for health and readiness endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded", "unhealthy")
    assert "version" in data
    assert "services" in data
    assert len(data["services"]) >= 1
    assert data["services"][0]["name"] == "postgresql"


def test_readiness_endpoint(client: TestClient):
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert "ready" in data
    assert isinstance(data["ready"], bool)
