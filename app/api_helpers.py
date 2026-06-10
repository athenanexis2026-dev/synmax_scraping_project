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

from app.api_config import CACHE_CONTROL, DEFAULT_DATABASE_PATH, DEFAULT_DOTENV_PATH


# COMMENT REPRESENTS AN ERROR TYPE
class DatabaseUnavailable(RuntimeError):
    """Raised when the configured SQLite database cannot be read."""


def database_mtime_ns(database_path: Path) -> int:
    """Return the SQLite file modified time for cache invalidation."""

    try:
        return database_path.stat().st_mtime_ns
    except OSError as error:
        raise DatabaseUnavailable(f"Database unavailable: {error}") from error


def resolve_database_path(database_path: Path | str | None) -> Path:
    """Resolve the database path from an override, environment variable, or default."""

    load_dotenv()
    configured_path = database_path or os.environ.get("SYNMAX_DATABASE_PATH", DEFAULT_DATABASE_PATH)
    return Path(configured_path).expanduser()


def load_dotenv(dotenv_path: Path | str = DEFAULT_DOTENV_PATH) -> None:
    """Load key-value pairs from a local .env file into the process environment."""

    path = Path(dotenv_path)
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def connect_readonly(database_path: Path) -> sqlite3.Connection:
    """Open a read-only SQLite connection with rows accessible by column name."""

    try:
        connection = sqlite3.connect(sqlite_readonly_uri(database_path), uri=True)
        connection.row_factory = sqlite3.Row
        return connection
    except (OSError, sqlite3.Error) as error:
        raise DatabaseUnavailable(f"Database unavailable: {error}") from error


def sqlite_readonly_uri(database_path: Path) -> str:
    """Build a SQLite URI that prevents accidentally creating or writing the database."""

    return f"{database_path.resolve().as_uri()}?mode=ro"


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
