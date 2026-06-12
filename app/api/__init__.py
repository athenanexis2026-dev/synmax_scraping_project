"""Compatibility facade for the FastAPI app entrypoint."""

from __future__ import annotations

from app.api.app_factory import app, create_app
from app.schemas.wells import normalize_hyphenated_api_number


# ============================================================================
# PUBLIC RE-EXPORTS
# ============================================================================
__all__ = ["app", "create_app", "normalize_hyphenated_api_number"]
