"""Helper functions for API configuration, database access, and cache responses."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from app.api_config import CACHE_CONTROL


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
