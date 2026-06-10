from app.normalize import normalize_record
from app.storage import (
    connect,
    count_wells,
    get_well,
    initialize_database,
    iter_wells_in_bounds,
    upsert_wells,
)


def test_initialize_and_upsert_wells(tmp_path) -> None:
    database_path = tmp_path / "sqlite.db"
    connection = connect(database_path)
    try:
        initialize_database(connection)
        record = normalize_record(
            {
                "API": "30-015-12345",
                "Current Operator": "Example Operator",
                "Latitude": "32.75",
                "Longitude": "-104.05",
            }
        )

        assert upsert_wells(connection, [record]) == 1

        well = get_well(connection, "3001512345")
        assert well is not None
        assert well["API"] == "3001512345"
        assert well["Operator"] == "Example Operator"
        assert well["Latitude"] == 32.75

        record["Operator"] = "Updated Operator"
        assert upsert_wells(connection, [record]) == 1
        assert get_well(connection, "3001512345")["Operator"] == "Updated Operator"
    finally:
        connection.close()


def test_count_and_iter_wells_in_bounds_excludes_null_coordinates(tmp_path) -> None:
    database_path = tmp_path / "sqlite.db"
    connection = connect(database_path)
    try:
        initialize_database(connection)
        records = [
            normalize_record(
                {
                    "API": "30-015-00001",
                    "Current Operator": "Inside Operator",
                    "Latitude": "32.50",
                    "Longitude": "-104.10",
                }
            ),
            normalize_record(
                {
                    "API": "30-015-00002",
                    "Current Operator": "Outside Operator",
                    "Latitude": "33.50",
                    "Longitude": "-104.10",
                }
            ),
            normalize_record(
                {
                    "API": "30-015-00003",
                    "Current Operator": "No Coordinates Operator",
                }
            ),
        ]

        assert upsert_wells(connection, records) == 3
        assert count_wells(connection) == 3

        candidates = iter_wells_in_bounds(connection, 32.0, 33.0, -105.0, -103.0)

        assert [candidate["API"] for candidate in candidates] == ["3001500001"]
        assert candidates[0]["Latitude"] == 32.5
        assert candidates[0]["Longitude"] == -104.1
    finally:
        connection.close()
