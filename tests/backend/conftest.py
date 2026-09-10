"""Pytest configuration and test fixtures for AgniNetra AI backend."""

from __future__ import annotations

import os
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure backend and root paths are available
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "backend"))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Set test environment
os.environ["ENVIRONMENT"] = "testing"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

# Configure GeoAlchemy2 for in-memory SQLite unit testing without SpatiaLite
try:
    import geoalchemy2.admin.dialects.sqlite as ga_sqlite
    ga_sqlite.after_create = lambda *args, **kwargs: None
    ga_sqlite.before_drop = lambda *args, **kwargs: None
    from geoalchemy2.types import _GISType
    _GISType.column_expression = lambda self, col: col
    _GISType.bind_expression = lambda self, val: val
except (ImportError, AttributeError):
    pass

from app.config import settings
from app.database import Base, get_db
from app.main import app

# SQLite in-memory engine for unit and API tests
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Create all tables for sqlite test runs."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session():
    """Yield an isolated database transaction per test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session: Session):
    """Provide a FastAPI TestClient configured with test DB override."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
