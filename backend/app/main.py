"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import settings
from app.middleware.error_handler import register_error_handlers
from app.middleware.logging_middleware import LoggingMiddleware
from app.utils.logging import setup_logging


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    setup_logging()

    application = FastAPI(
        title="AgniNetra AI",
        description="Industrial Thermal Intelligence and Fire Classification Platform",
        version="0.1.0",
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
    )

    # CORS
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request logging
    application.add_middleware(LoggingMiddleware)

    # Error handlers
    register_error_handlers(application)

    # Routes
    application.include_router(api_router)

    return application


app = create_app()
