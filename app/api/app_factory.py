"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.docs import APP_METADATA
from app.api.routes.health import router as health_router
from app.api.routes.wells import router as wells_router
from app.config.settings import get_database_path


# ============================================================================
# APPLICATION FACTORY
# ============================================================================
def create_app() -> FastAPI:
    """Create the API app with a configurable SQLite database path."""

    api = FastAPI(**APP_METADATA)
    api.state.database_path = get_database_path()
    api.include_router(health_router)
    api.include_router(wells_router)
    return api


app = create_app()

