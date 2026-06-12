"""Compatibility facade for Well Details URL helpers."""

from __future__ import annotations

from app.services.well_details.urls import (
    WELL_DETAILS_URL_TEMPLATE,
    build_well_details_url,
    hyphenate_api_number,
)


# ============================================================================
# PUBLIC RE-EXPORTS
# ============================================================================
__all__ = ["WELL_DETAILS_URL_TEMPLATE", "build_well_details_url", "hyphenate_api_number"]

