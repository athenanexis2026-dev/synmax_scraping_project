import os

from fastapi.testclient import TestClient

from app.api import _load_dotenv, create_app
from app.normalize import normalize_record
from app.schema import ASSIGNMENT_COLUMNS
from app.storage import connect, initialize_database, upsert_wells


def test_health_returns_database_status(tmp_path) -> None:
    client = TestClient(create_app(_build_database(tmp_path)))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected", "row_count": 4}


def test_load_dotenv_sets_database_path_without_overriding_existing_env(tmp_path, monkeypatch) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("SYNMAX_DATABASE_PATH=/tmp/from-dotenv.db\n", encoding="utf-8")
    monkeypatch.delenv("SYNMAX_DATABASE_PATH", raising=False)

    _load_dotenv(dotenv_path)

    assert os.environ["SYNMAX_DATABASE_PATH"] == "/tmp/from-dotenv.db"

    monkeypatch.setenv("SYNMAX_DATABASE_PATH", "/tmp/from-shell.db")
    _load_dotenv(dotenv_path)

    assert os.environ["SYNMAX_DATABASE_PATH"] == "/tmp/from-shell.db"


def test_health_returns_503_for_missing_database(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "missing.db"))

    response = client.get("/health")

    assert response.status_code == 503


def test_get_well_returns_exact_columns_and_cache_headers(tmp_path) -> None:
    client = TestClient(create_app(_build_database(tmp_path)))

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


def test_get_well_requires_hyphenated_api_number(tmp_path) -> None:
    client = TestClient(create_app(_build_database(tmp_path)))

    response = client.get("/well/3001525325")

    assert response.status_code == 422


def test_get_well_accepts_four_segment_hyphenated_api_number(tmp_path) -> None:
    client = TestClient(create_app(_build_database_with_snake_case_columns(tmp_path)))

    response = client.get("/well/30-015-45678-0000")

    assert response.status_code == 200
    assert response.json()["API"] == "30015456780000"
    assert response.json()["Operator"] == "Snake Case Operator"


def test_get_well_returns_404_for_missing_well(tmp_path) -> None:
    client = TestClient(create_app(_build_database(tmp_path)))

    response = client.get("/well/30-015-99999")

    assert response.status_code == 404


def test_wells_polygon_returns_sorted_api_numbers_and_cache_headers(tmp_path) -> None:
    client = TestClient(create_app(_build_database(tmp_path)))

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


def test_wells_polygon_rejects_two_distinct_points(tmp_path) -> None:
    client = TestClient(create_app(_build_database(tmp_path)))

    response = client.get("/wells/polygon?points=32,-105;33,-105")

    assert response.status_code == 422


def test_wells_polygon_rejects_malformed_points(tmp_path) -> None:
    client = TestClient(create_app(_build_database(tmp_path)))

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
