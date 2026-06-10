"""Helper functions for API configuration, database access, and cache responses."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from app.api_config import CACHE_CONTROL
from app.geo import parse_polygon_points, point_is_covered_by_polygon
from app.storage import get_well, iter_wells_in_bounds


class DatabaseUnavailable(RuntimeError):
    """Raised when the configured SQLite database cannot be read."""


# COMMENT THIS IS REALATED TO CACHE NEED TO UNDERSTAND WHY WE NEE THIS FOR THE LRU CACHE
def database_mtime_ns(database_path: Path) -> int:
    """Return the SQLite file modified time for cache invalidation."""

    try:
        return database_path.stat().st_mtime_ns
    except OSError as error:
        raise DatabaseUnavailable(f"Database unavailable: {error}") from error


def get_database_path() -> Path:
    """Return the database path configured in the environment."""

    try:
        database_path = os.environ["SYNMAX_DATABASE_PATH"]
    except KeyError as error:
        raise DatabaseUnavailable("SYNMAX_DATABASE_PATH must be set") from error
    return Path(database_path).expanduser()


# Read-only mode protects the database, prevents accidental writes, prevents accidental empty DB creation, and matches the API’s read-only design.
def connect_readonly(database_path: Path) -> sqlite3.Connection:
    """Open a read-only SQLite connection with rows accessible by column name."""

    try:
        readonly_uri = f"{database_path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(readonly_uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection
    except (OSError, sqlite3.Error) as error:
        raise DatabaseUnavailable(f"Database unavailable: {error}") from error


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


def json_cache_response(content: Any, request: Request) -> Response:
    """Return a JSON response with Cache-Control and ETag handling."""

    etag = build_etag(content)
    headers = {"Cache-Control": CACHE_CONTROL, "ETag": etag}
    if etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=content, headers=headers)


def build_etag(content: Any) -> str:
    """Build a stable ETag hash from response content."""

    payload = json.dumps(content, sort_keys=True, separators=(",", ":"), default=str).encode()
    digest = hashlib.sha256(payload).hexdigest()
    return f'"{digest}"'


def etag_matches(header_value: str | None, etag: str) -> bool:
    """Return whether an If-None-Match header contains the current ETag."""

    if not header_value:
        return False
    return any(candidate.strip() == etag for candidate in header_value.split(","))
