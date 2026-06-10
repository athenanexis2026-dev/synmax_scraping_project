import pytest

from app.geo import (
    PolygonValidationError,
    parse_polygon_points,
    point_is_covered_by_polygon,
)


def test_parse_polygon_points_closes_polygon_and_calculates_bounds() -> None:
    parsed = parse_polygon_points("32,-105;33,-105;33,-104;32,-104")

    assert parsed.coordinates[0] == parsed.coordinates[-1]
    assert parsed.min_latitude == 32
    assert parsed.max_latitude == 33
    assert parsed.min_longitude == -105
    assert parsed.max_longitude == -104


def test_point_is_covered_by_polygon_includes_boundary() -> None:
    parsed = parse_polygon_points("32,-105;33,-105;33,-104;32,-104")

    assert point_is_covered_by_polygon(parsed.polygon, 32.5, -104.5)
    assert point_is_covered_by_polygon(parsed.polygon, 32.0, -104.5)
    assert not point_is_covered_by_polygon(parsed.polygon, 34.0, -104.5)
    assert not point_is_covered_by_polygon(parsed.polygon, None, -104.5)


def test_parse_polygon_points_rejects_two_distinct_points() -> None:
    with pytest.raises(PolygonValidationError, match="at least three distinct"):
        parse_polygon_points("32,-105;33,-105")


def test_parse_polygon_points_rejects_out_of_range_coordinates() -> None:
    with pytest.raises(PolygonValidationError, match="latitude"):
        parse_polygon_points("91,-105;33,-105;33,-104")


def test_parse_polygon_points_rejects_self_intersection() -> None:
    with pytest.raises(PolygonValidationError, match="valid"):
        parse_polygon_points("0,0;1,1;1,0;0,1")
