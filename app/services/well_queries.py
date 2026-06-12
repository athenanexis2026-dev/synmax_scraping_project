"""Cached well query services used by the FastAPI routes."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.exceptions import DatabaseUnavailable
from app.repositories.sqlite import connect_readonly
from app.repositories.wells import get_well, iter_wells_in_bounds
from app.utils.geo import parse_polygon_points, point_is_covered_by_polygon


# ============================================================================
# DATABASE CACHE KEYS
# ============================================================================
def database_mtime_ns(database_path: Path) -> int:
    """Return the SQLite file modified time for cache invalidation."""

    try:
        return database_path.stat().st_mtime_ns
    except OSError as error:
        raise DatabaseUnavailable(f"Database unavailable: {error}") from error


# ============================================================================
# WELL LOOKUPS
# ============================================================================
def read_cached_well(database_path: Path, normalized_api: str) -> dict[str, Any] | None:
    """Return one well using the database modified time as part of the cache key."""

    return _cached_get_well(
        str(database_path),
        database_mtime_ns(database_path),
        normalized_api,
    )


@lru_cache(maxsize=512)
def _cached_get_well(
    database_path: str,
    database_mtime_ns: int,
    normalized_api: str,
) -> dict[str, Any] | None:
    del database_mtime_ns
    connection = connect_readonly(Path(database_path))
    try:
        return get_well(connection, normalized_api)
    finally:
        connection.close()


# ============================================================================
# POLYGON LOOKUPS
# ============================================================================
def read_cached_polygon_api_numbers(database_path: Path, points: str) -> list[str]:
    """Return API numbers inside a polygon using the database modified time cache key."""

    return _cached_polygon_api_numbers(
        str(database_path),
        database_mtime_ns(database_path),
        points,
    )


@lru_cache(maxsize=128)
def _cached_polygon_api_numbers(
    database_path: str,
    database_mtime_ns: int,
    points: str,
) -> list[str]:
    del database_mtime_ns
    parsed_polygon = parse_polygon_points(points)
    connection = connect_readonly(Path(database_path))
    try:
        candidates = iter_wells_in_bounds(
            connection,
            parsed_polygon.min_latitude,
            parsed_polygon.max_latitude,
            parsed_polygon.min_longitude,
            parsed_polygon.max_longitude,
        )
    finally:
        connection.close()

    matching_api_numbers = [
        str(candidate["API"])
        for candidate in candidates
        if point_is_covered_by_polygon(
            parsed_polygon.polygon,
            candidate["Latitude"],
            candidate["Longitude"],
        )
    ]
    return sorted(matching_api_numbers)

