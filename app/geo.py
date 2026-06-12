"""Compatibility facade for geospatial helpers."""

from __future__ import annotations

from app.utils.geo import (
    ParsedPolygon,
    PolygonValidationError,
    parse_polygon_points,
    point_is_covered_by_polygon,
)


# ============================================================================
# PUBLIC RE-EXPORTS
# ============================================================================
__all__ = [
    "ParsedPolygon",
    "PolygonValidationError",
    "parse_polygon_points",
    "point_is_covered_by_polygon",
]

