from app.normalize import normalize_record
from app.storage import connect, get_well, initialize_database, upsert_wells


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
