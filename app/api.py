"""FastAPI service for read-only well-data access."""
from __future__ import annotations

# fastapi is the web framework we are using to build the API.
from fastapi import FastAPI, HTTPException, Path as ApiPath, Query as ApiQuery, Request
from fastapi.responses import Response

from app.api_config import (
    APP_METADATA,
    API_NUMBER_DESCRIPTION,
    API_NUMBER_ERROR,
    API_NUMBER_EXAMPLES,
    API_NUMBER_PATTERN,
    API_NUMBER_PATTERN_TEXT,
    POLYGON_POINTS_DESCRIPTION,
    POLYGON_POINTS_EXAMPLES,
    POLYGON_ROUTE_RESPONSES,
    WELL_ROUTE_RESPONSES,
)
from app.api_helpers import (
    DatabaseUnavailable,
    connect_readonly,
    get_database_path,
    json_cache_response,
    read_cached_polygon_api_numbers,
    read_cached_well,
)
from app.geo import PolygonValidationError


def create_app() -> FastAPI:
    """Create the API app with a configurable SQLite database path."""

    # is creating the FastAPI application.
    # FastAPI(...) is the constructor that builds the API app.
    api = FastAPI(**APP_METADATA)
    resolved_database_path = get_database_path()
    api.state.database_path = resolved_database_path

    @api.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        try:
            connection = connect_readonly(resolved_database_path)
            try:
                connection.execute("SELECT 1 FROM api_well_data LIMIT 1").fetchone()
            finally:
                connection.close()
        except DatabaseUnavailable as error:
            raise HTTPException(status_code=503, message=str(error)) from error

        return {"status": "ok", "database": "connected"}

    @api.get(
        "/well/{api_number}",
        tags=["wells"],
        summary="Get one well by API number",
        response_description="A single well record.",
        responses=WELL_ROUTE_RESPONSES,
    )
    def read_well(
        request: Request,
        api_number: str = ApiPath(
            pattern=API_NUMBER_PATTERN_TEXT,
            description=API_NUMBER_DESCRIPTION,
            examples=API_NUMBER_EXAMPLES,
        ),
    ) -> Response:
        normalized_api = normalize_hyphenated_api_number(api_number)

        try:
            well = read_cached_well(resolved_database_path, normalized_api)
        except DatabaseUnavailable as error:
            raise HTTPException(status_code=503, message=str(error)) from error

        if well is None:
            raise HTTPException(status_code=404, message="Well not found")

        return json_cache_response(well, request)

    @api.get(
        "/wells/polygon",
        tags=["wells"],
        summary="Find wells inside a polygon",
        response_description="A sorted list of API numbers inside the polygon.",
        responses=POLYGON_ROUTE_RESPONSES,
    )
    def wells_in_polygon(
        request: Request,
        points: str = ApiQuery(
            description=POLYGON_POINTS_DESCRIPTION,
            examples=POLYGON_POINTS_EXAMPLES,
        ),
    ) -> Response:
        try:
            api_numbers = read_cached_polygon_api_numbers(resolved_database_path, points)
        except PolygonValidationError as error:
            raise HTTPException(status_code=422, message=str(error)) from error
        except DatabaseUnavailable as error:
            raise HTTPException(status_code=503, message=str(error)) from error

        return json_cache_response(
            {"api_numbers": api_numbers, "count": len(api_numbers)},
            request,
        )

    return api


def normalize_hyphenated_api_number(api_number: str) -> str:
    """Validate a public hyphenated API number and return its digit-only storage key."""

    if not API_NUMBER_PATTERN.fullmatch(api_number):
        raise HTTPException(status_code=422, message=API_NUMBER_ERROR)
    return api_number.replace("-", "")

app = create_app()
