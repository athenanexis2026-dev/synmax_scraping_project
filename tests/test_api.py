import os

from fastapi.testclient import TestClient

os.environ.setdefault("SYNMAX_DATABASE_PATH", "api_well_data.db")

from app.main import create_app
from app.repositories.schema import ASSIGNMENT_COLUMNS
from app.repositories.wells import connect, initialize_database, upsert_wells
from app.utils.normalize import normalize_record


def test_health_returns_database_status(tmp_path, monkeypatch) -> None:
    client = _client_for_database(_build_database(tmp_path), monkeypatch)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


def test_health_returns_503_for_missing_database(tmp_path, monkeypatch) -> None:
    client = _client_for_database(tmp_path / "missing.db", monkeypatch)

    response = client.get("/health")

    assert response.status_code == 503


def test_get_well_returns_exact_columns_and_cache_headers(tmp_path, monkeypatch) -> None:
    client = _client_for_database(_build_database(tmp_path), monkeypatch)

    response = client.get("/well/30-015-25325")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300"
    assert response.headers["etag"]
    assert set(response.json()) == set(ASSIGNMENT_COLUMNS)
    assert response.json()["API"] == "3001525325"
    assert response.json()["Operator"] == "Inside Operator"

    cached_response = client.get(
        "/well/30-015-25325",
        headers={"If-None-Match": response.headers["etag"]},
    )

    assert cached_response.status_code == 304


def test_get_well_openapi_contract_documents_api_number_formats(tmp_path, monkeypatch) -> None:
    client = _client_for_database(_build_database(tmp_path), monkeypatch)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    well_operation = response.json()["paths"]["/well/{api_number}"]["get"]
    parameter = well_operation["parameters"][0]
    assert well_operation["summary"] == "Get one well by API number"
    assert parameter["name"] == "api_number"
    assert parameter["schema"]["pattern"] == r"^\d{2}-\d{3}-\d{5}(?:-\d{4})?$"
    assert "30-015-45678-0000" in parameter["schema"]["examples"]


def test_get_well_requires_hyphenated_api_number(tmp_path, monkeypatch) -> None:
    client = _client_for_database(_build_database(tmp_path), monkeypatch)

    response = client.get("/well/3001525325")

    assert response.status_code == 422


def test_get_well_accepts_four_segment_hyphenated_api_number(tmp_path, monkeypatch) -> None:
    client = _client_for_database(_build_database_with_snake_case_columns(tmp_path), monkeypatch)

    response = client.get("/well/30-015-45678-0000")

    assert response.status_code == 200
    assert response.json()["API"] == "30015456780000"
    assert response.json()["Operator"] == "Snake Case Operator"


def test_get_well_returns_404_for_missing_well(tmp_path, monkeypatch) -> None:
    client = _client_for_database(_build_database(tmp_path), monkeypatch)

    response = client.get("/well/30-015-99999")

    assert response.status_code == 404


def test_wells_polygon_returns_sorted_api_numbers_and_cache_headers(tmp_path, monkeypatch) -> None:
    client = _client_for_database(_build_database(tmp_path), monkeypatch)

    response = client.get("/wells/polygon?points=32,-105;33,-105;33,-104;32,-104")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300"
    assert response.headers["etag"]
    assert response.json() == {"api_numbers": ["3001525325", "3001525326"], "count": 2}

    cached_response = client.get(
        "/wells/polygon?points=32,-105;33,-105;33,-104;32,-104",
        headers={"If-None-Match": response.headers["etag"]},
    )

    assert cached_response.status_code == 304


def test_wells_polygon_openapi_contract_documents_points_format(tmp_path, monkeypatch) -> None:
    client = _client_for_database(_build_database(tmp_path), monkeypatch)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    polygon_operation = response.json()["paths"]["/wells/polygon"]["get"]
    parameter = polygon_operation["parameters"][0]
    assert polygon_operation["summary"] == "Find wells inside a polygon"
    assert parameter["name"] == "points"
    assert "latitude,longitude" in parameter["schema"]["description"]
    assert "32,-105;33,-105;33,-104;32,-104" in parameter["schema"]["examples"]


def test_wells_polygon_requires_points_query_parameter(tmp_path, monkeypatch) -> None:
    client = _client_for_database(_build_database(tmp_path), monkeypatch)

    response = client.get("/wells/polygon")

    assert response.status_code == 422


def test_wells_polygon_rejects_two_distinct_points(tmp_path, monkeypatch) -> None:
    client = _client_for_database(_build_database(tmp_path), monkeypatch)

    response = client.get("/wells/polygon?points=32,-105;33,-105")

    assert response.status_code == 422


def test_wells_polygon_rejects_malformed_points(tmp_path, monkeypatch) -> None:
    client = _client_for_database(_build_database(tmp_path), monkeypatch)

    response = client.get("/wells/polygon?points=32,-105;nope;33,-104")

    assert response.status_code == 422


def _build_database(tmp_path):
    database_path = tmp_path / "sqlite.db"
    connection = connect(database_path)
    try:
        initialize_database(connection)
        upsert_wells(
            connection,
            [
                normalize_record(
                    {
                        "API": "30-015-25325",
                        "Current Operator": "Inside Operator",
                        "Latitude": "32.50",
                        "Longitude": "-104.50",
                    }
                ),
                normalize_record(
                    {
                        "API": "30-015-25326",
                        "Current Operator": "Boundary Operator",
                        "Latitude": "32.00",
                        "Longitude": "-104.50",
                    }
                ),
                normalize_record(
                    {
                        "API": "30-015-25327",
                        "Current Operator": "Outside Operator",
                        "Latitude": "33.50",
                        "Longitude": "-104.50",
                    }
                ),
                normalize_record(
                    {
                        "API": "30-015-25328",
                        "Current Operator": "No Coordinates Operator",
                    }
                ),
            ],
        )
    finally:
        connection.close()
    return database_path


def _client_for_database(database_path, monkeypatch):
    monkeypatch.setenv("SYNMAX_DATABASE_PATH", str(database_path))
    return TestClient(create_app())


def _build_database_with_snake_case_columns(tmp_path):
    database_path = tmp_path / "snake_case.db"
    connection = connect(database_path)
    try:
        connection.execute(
            """
            CREATE TABLE api_well_data (
                operator TEXT,
                api TEXT,
                latitude REAL,
                longitude REAL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO api_well_data (operator, api, latitude, longitude)
            VALUES (?, ?, ?, ?)
            """,
            ("Snake Case Operator", "30015456780000", 32.2, -103.6),
        )
        connection.commit()
    finally:
        connection.close()
    return database_path
