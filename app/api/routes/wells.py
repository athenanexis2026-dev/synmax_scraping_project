"""Well lookup and polygon search routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path as ApiPath, Query as ApiQuery, Request
from fastapi.responses import Response

from app.api.docs import (
    API_NUMBER_DESCRIPTION,
    API_NUMBER_EXAMPLES,
    API_NUMBER_PATTERN_TEXT,
    POLYGON_POINTS_DESCRIPTION,
    POLYGON_POINTS_EXAMPLES,
    POLYGON_ROUTE_RESPONSES,
    WELL_ROUTE_RESPONSES,
)
from app.core.cache import json_cache_response
from app.core.exceptions import DatabaseUnavailable
from app.schemas.wells import normalize_hyphenated_api_number
from app.services.well_queries import read_cached_polygon_api_numbers, read_cached_well
from app.utils.geo import PolygonValidationError

router = APIRouter(tags=["wells"])


# ============================================================================
# WELL ROUTES
# ============================================================================
@router.get(
    "/well/{api_number}",
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
    database_path = request.app.state.database_path

    try:
        well = read_cached_well(database_path, normalized_api)
    except DatabaseUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    if well is None:
        raise HTTPException(status_code=404, detail="Well not found")

    return json_cache_response(well, request)


@router.get(
    "/wells/polygon",
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
    database_path = request.app.state.database_path
    try:
        api_numbers = read_cached_polygon_api_numbers(database_path, points)
    except PolygonValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except DatabaseUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    return json_cache_response(
        {"api_numbers": api_numbers, "count": len(api_numbers)},
        request,
    )
