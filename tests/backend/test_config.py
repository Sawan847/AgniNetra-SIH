"""Unit tests for backend configuration and settings."""

from __future__ import annotations

from app.config import Settings


def test_default_settings():
    s = Settings(
        database_url="postgresql://user:pass@localhost:5432/testdb",
        environment="development",
        cors_origins="http://localhost:5173,http://localhost:3000",
    )
    assert s.environment == "development"
    assert s.is_development is True
    assert "http://localhost:5173" in s.cors_origin_list
    assert "http://localhost:3000" in s.cors_origin_list


def test_cors_origin_list_parsing():
    s = Settings(cors_origins="http://example.com , http://test.com  ")
    assert s.cors_origin_list == ["http://example.com", "http://test.com"]
