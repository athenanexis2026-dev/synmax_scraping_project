"""Compatibility facade for API helpers."""

from __future__ import annotations

from app.config.settings import get_database_path
from app.core.cache import build_etag, etag_matches, json_cache_response
from app.core.exceptions import DatabaseUnavailable
from app.repositories.sqlite import connect_readonly
from app.services.well_queries import (
    database_mtime_ns,
    read_cached_polygon_api_numbers,
    read_cached_well,
)


# ============================================================================
# PUBLIC RE-EXPORTS
# ============================================================================
__all__ = [
    "DatabaseUnavailable",
    "build_etag",
    "connect_readonly",
    "database_mtime_ns",
    "etag_matches",
    "get_database_path",
    "json_cache_response",
    "read_cached_polygon_api_numbers",
    "read_cached_well",
]

