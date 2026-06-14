"""ASGI entrypoint for the SynMax Well Data API."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.docs import APP_METADATA
from app.api.routes.health import router as health_router
from app.api.routes.wells import router as wells_router
from app.repositories.sqlite import DatabaseUnavailable
from app.schemas.wells import API_NUMBER_ERROR


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
# VALIDATION ERRORS
# ============================================================================
async def readable_validation_exception_handler(
    request: Request,
    error: RequestValidationError,
) -> JSONResponse:
    """Return a human-readable message for public API number format errors."""

    for validation_error in error.errors():
        if tuple(validation_error.get("loc", ())) == ("path", "api_number"):
            return JSONResponse(status_code=422, content={"detail": API_NUMBER_ERROR})

    return await request_validation_exception_handler(request, error)


# ============================================================================
# APPLICATION FACTORY
# ============================================================================
def create_app() -> FastAPI:
    """Create the API app with a configurable SQLite database path."""

    api = FastAPI(**APP_METADATA)
    api.state.database_path = get_database_path()
    api.add_exception_handler(
        RequestValidationError,
        readable_validation_exception_handler,
    )
    api.include_router(health_router)
    api.include_router(wells_router)
    return api


app = create_app()
