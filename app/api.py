"""FastAPI service for read-only well-data access."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

# fastapi is the web framework we are using to build the API.
from fastapi import FastAPI, HTTPException, Path as ApiPath, Request
from fastapi.responses import Response

from app.api_config import (
    APP_METADATA,
    API_NUMBER_DESCRIPTION,
    API_NUMBER_ERROR,
    API_NUMBER_PATTERN,
    API_NUMBER_PATTERN_TEXT,
    WELL_RESPONSE_EXAMPLE,
)
from app.api_helpers import (
    DatabaseUnavailable,
    connect_readonly,
    database_mtime_ns,
    json_cache_response,
    resolve_database_path,
)
from app.geo import PolygonValidationError, parse_polygon_points, point_is_covered_by_polygon
from app.storage import get_well, iter_wells_in_bounds


def create_app(database_path: Path | str | None = None) -> FastAPI:
    """Create the API app with a configurable SQLite database path."""

    # is creating the FastAPI application.
    # FastAPI(...) is the constructor that builds the API app.
    api = FastAPI(**APP_METADATA)
    resolved_database_path = resolve_database_path(database_path)
    api.state.database_path = resolved_database_path

    @api.get("/health", tags=["health"])
    def health(request: Request) -> dict[str, str]:
        try:
            connection = connect_readonly(resolved_database_path)
            try:
                connection.execute("SELECT 1 FROM api_well_data LIMIT 1").fetchone()
            finally:
                connection.close()
        except DatabaseUnavailable as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

        return {"status": "ok", "database": "connected"}

    @api.get(
        "/well/{api_number}",
        tags=["wells"],
        summary="Get one well by API number",
        response_description="A single well record using the assignment field names.",
        responses={
            200: {
                "description": "Well found.",
                "content": {"application/json": {"example": WELL_RESPONSE_EXAMPLE}},
            },
            304: {"description": "The cached client copy is still current."},
            404: {"description": "The API number is well-formed but no row exists."},
            422: {"description": "The API number is not hyphenated correctly."},
            503: {"description": "The configured SQLite database is unavailable."},
        },
    )
    def read_well(
        request: Request,
        api_number: str = ApiPath(
            pattern=API_NUMBER_PATTERN_TEXT,
            description=API_NUMBER_DESCRIPTION,
            examples=["30-015-25325", "30-015-45678-0000"],
        ),
    ) -> Response:
        normalized_api = normalize_hyphenated_api_number(api_number)

        try:
            well = _cached_get_well(
                str(resolved_database_path),
                database_mtime_ns(resolved_database_path),
                normalized_api,
            )
        except DatabaseUnavailable as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

        if well is None:
            raise HTTPException(status_code=404, detail="Well not found")

        return json_cache_response(well, request)

    @api.get("/wells/polygon", tags=["wells"])
    def wells_in_polygon(points: str, request: Request) -> Response:
        try:
            parse_polygon_points(points)
        except PolygonValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

        try:
            api_numbers = _cached_polygon_api_numbers(
                str(resolved_database_path),
                database_mtime_ns(resolved_database_path),
                points,
            )
        except DatabaseUnavailable as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

        return json_cache_response(
            {"api_numbers": api_numbers, "count": len(api_numbers)},
            request,
        )

    return api


def normalize_hyphenated_api_number(api_number: str) -> str:
    """Validate a public hyphenated API number and return its digit-only storage key."""

    if not API_NUMBER_PATTERN.fullmatch(api_number):
        raise HTTPException(status_code=422, detail=API_NUMBER_ERROR)
    return api_number.replace("-", "")


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


app = create_app()
