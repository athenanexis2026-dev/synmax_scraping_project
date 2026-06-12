"""Health and readiness routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.core.exceptions import DatabaseUnavailable
from app.repositories.sqlite import connect_readonly

router = APIRouter(tags=["health"])


# ============================================================================
# HEALTH ROUTES
# ============================================================================
@router.get("/health")
def health(request: Request) -> dict[str, str]:
    database_path = request.app.state.database_path
    try:
        connection = connect_readonly(database_path)
        try:
            connection.execute("SELECT 1 FROM api_well_data LIMIT 1").fetchone()
        finally:
            connection.close()
    except DatabaseUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    return {"status": "ok", "database": "connected"}

