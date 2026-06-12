"""ASGI entrypoint for the SynMax Well Data API."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from app.api.docs import APP_METADATA
from app.api.routes.health import router as health_router
from app.api.routes.wells import router as wells_router
from app.repositories.sqlite import DatabaseUnavailable


# ============================================================================
# DATABASE SETTINGS
# ============================================================================
def get_database_path() -> Path:
    """Return the database path configured in the environment."""

    try:
        database_path = os.environ["SYNMAX_DATABASE_PATH"]
    except KeyError as error:
        raise DatabaseUnavailable("SYNMAX_DATABASE_PATH must be set") from error
    return Path(database_path).expanduser()


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
