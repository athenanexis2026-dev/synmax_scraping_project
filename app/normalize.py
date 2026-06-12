"""Compatibility facade for normalization utilities."""

from __future__ import annotations

from app.utils.normalize import (
    API_DIGITS,
    FIELD_MAPPING,
    LOCATION_FIELDS,
    build_surface_location,
    normalize_api_number,
    normalize_record,
    normalize_records,
    read_api_numbers,
    read_source_records,
)


# ============================================================================
# PUBLIC RE-EXPORTS
# ============================================================================
__all__ = [
    "API_DIGITS",
    "FIELD_MAPPING",
    "LOCATION_FIELDS",
    "build_surface_location",
    "normalize_api_number",
    "normalize_record",
    "normalize_records",
    "read_api_numbers",
    "read_source_records",
]

