"""ASGI entrypoint for the SynMax Well Data API."""

from __future__ import annotations

from app.api.app_factory import app, create_app


# ============================================================================
# PUBLIC ASGI APP
# ============================================================================
__all__ = ["app", "create_app"]
