"""Geospatial parsing and matching helpers for well searches."""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import Point, Polygon


class PolygonValidationError(ValueError):
    """Raised when user-provided polygon coordinates cannot form a valid polygon."""


@dataclass(frozen=True)
class ParsedPolygon:
    """Validated polygon query input with its latitude/longitude bounds."""

    polygon: Polygon
    coordinates: tuple[tuple[float, float], ...]
    min_latitude: float
    max_latitude: float
    min_longitude: float
    max_longitude: float


def parse_polygon_points(points: str) -> ParsedPolygon:
    """Parse a semicolon-delimited ``lat,lon`` string into a valid polygon."""

    if not points or not points.strip():
        raise PolygonValidationError("points is required")

    raw_pairs = points.split(";")
    if any(not pair.strip() for pair in raw_pairs):
        raise PolygonValidationError("points must not contain empty coordinate pairs")

    coordinates = tuple(_parse_coordinate_pair(pair) for pair in raw_pairs)
    distinct_coordinates = set(coordinates)
    if len(distinct_coordinates) < 3:
        raise PolygonValidationError("polygon requires at least three distinct coordinate pairs")

    closed_coordinates = coordinates
    if coordinates[0] != coordinates[-1]:
        closed_coordinates = (*coordinates, coordinates[0])

    polygon = Polygon((longitude, latitude) for latitude, longitude in closed_coordinates)
    if polygon.is_empty or not polygon.is_valid or polygon.area == 0:
        raise PolygonValidationError("points must form a valid non-self-intersecting polygon")

    min_longitude, min_latitude, max_longitude, max_latitude = polygon.bounds
    return ParsedPolygon(
        polygon=polygon,
        coordinates=closed_coordinates,
        min_latitude=min_latitude,
        max_latitude=max_latitude,
        min_longitude=min_longitude,
        max_longitude=max_longitude,
    )


def point_is_covered_by_polygon(
    polygon: Polygon,
    latitude: float | None,
    longitude: float | None,
) -> bool:
    """Return whether a latitude/longitude point is inside or on a polygon boundary."""

    if latitude is None or longitude is None:
        return False
    return polygon.covers(Point(longitude, latitude))


def _parse_coordinate_pair(raw_pair: str) -> tuple[float, float]:
    pieces = [piece.strip() for piece in raw_pair.split(",")]
    if len(pieces) != 2 or not pieces[0] or not pieces[1]:
        raise PolygonValidationError("each point must use the format lat,lon")

    try:
        latitude = float(pieces[0])
        longitude = float(pieces[1])
    except ValueError as error:
        raise PolygonValidationError("latitude and longitude must be numeric") from error

    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise PolygonValidationError("latitude and longitude must be finite")
    if not -90 <= latitude <= 90:
        raise PolygonValidationError("latitude must be between -90 and 90")
    if not -180 <= longitude <= 180:
        raise PolygonValidationError("longitude must be between -180 and 180")

    return latitude, longitude

