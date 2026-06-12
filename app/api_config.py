"""Compatibility facade for API documentation and cache constants."""

from __future__ import annotations

from app.api.docs import (
    API_NUMBER_DESCRIPTION,
    API_NUMBER_ERROR,
    API_NUMBER_EXAMPLES,
    API_NUMBER_PATTERN,
    API_NUMBER_PATTERN_TEXT,
    APP_METADATA,
    POLYGON_POINTS_DESCRIPTION,
    POLYGON_POINTS_EXAMPLES,
    POLYGON_RESPONSE_EXAMPLE,
    POLYGON_ROUTE_RESPONSES,
    WELL_RESPONSE_EXAMPLE,
    WELL_ROUTE_RESPONSES,
)
from app.config.api import CACHE_CONTROL


# ============================================================================
# PUBLIC RE-EXPORTS
# ============================================================================
__all__ = [
    "API_NUMBER_DESCRIPTION",
    "API_NUMBER_ERROR",
    "API_NUMBER_EXAMPLES",
    "API_NUMBER_PATTERN",
    "API_NUMBER_PATTERN_TEXT",
    "APP_METADATA",
    "CACHE_CONTROL",
    "POLYGON_POINTS_DESCRIPTION",
    "POLYGON_POINTS_EXAMPLES",
    "POLYGON_RESPONSE_EXAMPLE",
    "POLYGON_ROUTE_RESPONSES",
    "WELL_RESPONSE_EXAMPLE",
    "WELL_ROUTE_RESPONSES",
]

