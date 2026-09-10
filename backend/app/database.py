"""SQLAlchemy database engine, session factory, and dependency."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any, Dict

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


def _patch_geoalchemy_for_sqlite() -> None:
    """Let Geometry columns behave as plain text on SQLite.

    PostGIS is the production target, but a local demo without Docker runs on
    SQLite, which has none of the spatial functions. geoalchemy2 otherwise emits
    AsEWKB(geom) on every SELECT and each query fails with "no such function".

    Geometry columns become opaque WKT strings under this patch. Nothing in the
    application performs spatial SQL - distance work happens in the feature pipeline
    with a BallTree - so the only requirement is that the column round-trips.

    Applied only for SQLite URLs; PostgreSQL is untouched.
    """
    try:
        import geoalchemy2.admin.dialects.sqlite as ga_sqlite
        from geoalchemy2.types import _GISType
    except (ImportError, AttributeError):  # geoalchemy2 absent or restructured
        return

    ga_sqlite.after_create = lambda *args, **kwargs: None
    ga_sqlite.before_drop = lambda *args, **kwargs: None
    _GISType.column_expression = lambda self, col: col
    _GISType.bind_expression = lambda self, val: val

    # The result processor must be neutralised too. Without this, geoalchemy2 still
    # wraps every value it reads back into a WKBElement, which calls
    # binascii.unhexlify on our plain-text WKT and fails with
    # "Non-hexadecimal digit found" on any query touching a geometry column.
    _GISType.result_processor = lambda self, dialect, coltype: None


if settings.database_url.startswith("sqlite"):
    _patch_geoalchemy_for_sqlite()

# Configure engine parameters depending on DB backend (PostgreSQL vs SQLite)
# SQL echo is opt-in via SQL_ECHO rather than tied to development mode. Echoing
# every statement made bulk ingestion unreadable and buried real warnings.
engine_kwargs: Dict[str, Any] = {"echo": settings.sql_echo}
if settings.database_url.startswith("postgresql"):
    engine_kwargs.update({
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
    })

engine = create_engine(settings.database_url, **engine_kwargs)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session and closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
