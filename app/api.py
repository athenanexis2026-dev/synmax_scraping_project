"""FastAPI service for read-only well-data access."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from app.geo import PolygonValidationError, parse_polygon_points, point_is_covered_by_polygon
from app.storage import count_wells, get_well, iter_wells_in_bounds


API_NUMBER_PATTERN = re.compile(r"^\d{2}-\d{3}-\d{5}(?:-\d{4})?$")
CACHE_CONTROL = "public, max-age=300"
DEFAULT_DATABASE_PATH = "sqlite.db"
DEFAULT_DOTENV_PATH = ".env"


class DatabaseUnavailable(RuntimeError):
    """Raised when the configured SQLite database cannot be read."""


def create_app(database_path: Path | str | None = None) -> FastAPI:
    """Create the API app with a configurable SQLite database path."""

    api = FastAPI(title="SynMax Well Data API")
    api.state.database_path = _resolve_database_path(database_path)

    @api.get("/health")
    def health(request: Request) -> dict[str, Any]:
        path = _database_path(request)
        try:
            connection = _connect_readonly_or_raise(path)
            try:
                row_count = count_wells(connection)
            finally:
                connection.close()
        except DatabaseUnavailable as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

        return {"status": "ok", "database": "connected", "row_count": row_count}

    @api.get("/well/{api_number}")
    def read_well(api_number: str, request: Request) -> Response:
        normalized_api = normalize_hyphenated_api_number(api_number)
        path = _database_path(request)

        try:
            well = _cached_get_well(str(path), _database_mtime_ns(path), normalized_api)
        except DatabaseUnavailable as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

        if well is None:
            raise HTTPException(status_code=404, detail="Well not found")

        return _json_cache_response(well, request)

    @api.get("/wells/polygon")
    def wells_in_polygon(points: str, request: Request) -> Response:
        try:
            parse_polygon_points(points)
        except PolygonValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

        path = _database_path(request)
        try:
            api_numbers = _cached_polygon_api_numbers(str(path), _database_mtime_ns(path), points)
        except DatabaseUnavailable as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

        return _json_cache_response(
            {"api_numbers": api_numbers, "count": len(api_numbers)},
            request,
        )

    return api


def normalize_hyphenated_api_number(api_number: str) -> str:
    """Validate a public hyphenated API number and return its digit-only storage key."""

    if not API_NUMBER_PATTERN.fullmatch(api_number):
        raise HTTPException(
            status_code=422,
            detail="api_number must use the hyphenated format 30-015-25325",
        )
    return api_number.replace("-", "")


@lru_cache(maxsize=512)
def _cached_get_well(
    database_path: str,
    database_mtime_ns: int,
    normalized_api: str,
) -> dict[str, Any] | None:
    del database_mtime_ns
    connection = _connect_or_raise(database_path)
    try:
        return get_well(connection, normalized_api)
    finally:
        connection.close()


@lru_cache(maxsize=128)
def _cached_polygon_api_numbers(
    database_path: str,
    database_mtime_ns: int,
    points: str,
) -> list[str]:
    del database_mtime_ns
    parsed_polygon = parse_polygon_points(points)
    connection = _connect_or_raise(database_path)
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


def _connect_or_raise(database_path: str) -> sqlite3.Connection:
    return _connect_readonly_or_raise(Path(database_path))


def _connect_readonly_or_raise(database_path: Path) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(_sqlite_readonly_uri(database_path), uri=True)
        connection.row_factory = sqlite3.Row
        return connection
    except (OSError, sqlite3.Error) as error:
        raise DatabaseUnavailable(f"Database unavailable: {error}") from error


def _database_path(request: Request) -> Path:
    return request.app.state.database_path


def _database_mtime_ns(database_path: Path) -> int:
    try:
        return database_path.stat().st_mtime_ns
    except OSError as error:
        raise DatabaseUnavailable(f"Database unavailable: {error}") from error


def _resolve_database_path(database_path: Path | str | None) -> Path:
    _load_dotenv()
    configured_path = database_path or os.environ.get("SYNMAX_DATABASE_PATH", DEFAULT_DATABASE_PATH)
    return Path(configured_path).expanduser()


def _load_dotenv(dotenv_path: Path | str = DEFAULT_DOTENV_PATH) -> None:
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


def _sqlite_readonly_uri(database_path: Path) -> str:
    return f"{database_path.resolve().as_uri()}?mode=ro"


def _json_cache_response(content: Any, request: Request) -> Response:
    etag = _build_etag(content)
    headers = {"Cache-Control": CACHE_CONTROL, "ETag": etag}
    if _etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=content, headers=headers)


def _build_etag(content: Any) -> str:
    payload = json.dumps(content, sort_keys=True, separators=(",", ":"), default=str).encode()
    digest = hashlib.sha256(payload).hexdigest()
    return f'"{digest}"'


def _etag_matches(header_value: str | None, etag: str) -> bool:
    if not header_value:
        return False
    return any(candidate.strip() == etag for candidate in header_value.split(","))


app = create_app()
