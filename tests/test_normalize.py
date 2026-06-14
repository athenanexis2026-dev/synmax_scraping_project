from app.utils.normalize import (
    normalize_api_number,
    normalize_record,
    normalize_records,
    read_api_numbers,
)


def test_normalize_api_number_keeps_digits_only() -> None:
    assert normalize_api_number("30-015-12345") == "3001512345"
    assert normalize_api_number(" 3001512345 ") == "3001512345"
    assert normalize_api_number("") is None


def test_read_api_numbers_handles_one_column_header(tmp_path) -> None:
    csv_path = tmp_path / "apis.csv"
    csv_path.write_text("api\n30-045-35432\n", encoding="utf-8")

    assert read_api_numbers(csv_path) == {"3004535432"}


def test_normalize_record_maps_export_fields_and_types() -> None:
    record = normalize_record(
        {
            "Current Operator": "Example Operator",
            "Status": "Active",
            "Type": "Oil",
            "Work Type": "New",
            "Mineral Owner": "Federal",
            "Surface Owner": "State",
            "Projection": "NAD83",
            "True Vertical Depth": "10,250",
            "Elevation": "3210.0",
            "Kelly Bushing": "",
            "Drilling Floor": "3221",
            "Spud Date": "2020-01-02",
            "Last Inspection": "2024-05-06",
            "Latitude": "32.75",
            "Longitude": "-104.05",
            "API": "30-015-12345",
            "Section": "12",
            "Township": "18S",
            "Range": "29E",
        }
    )

    assert record["API"] == "3001512345"
    assert record["Operator"] == "Example Operator"
    assert record["Well Type"] == "Oil"
    assert record["TVD"] == 10250
    assert record["GL Elevation"] == 3210
    assert record["KB Elevation"] is None
    assert record["Latitude"] == 32.75
    assert record["Longitude"] == -104.05
    assert record["Surface Location"] == "Section: 12; Township: 18S; Range: 29E"
    assert record["Directional Status"] is None


def test_normalize_record_prefers_assignment_columns_over_export_aliases() -> None:
    record = normalize_record(
        {
            "API": "30-015-12345",
            "Operator": "Assignment Operator",
            "Current Operator": "Export Operator",
            "Well Type": "Gas",
            "Type": "Oil",
            "CRS": "EPSG:4326",
            "Projection": "NAD83",
        }
    )

    assert record["Operator"] == "Assignment Operator"
    assert record["Well Type"] == "Gas"
    assert record["CRS"] == "EPSG:4326"


def test_normalize_record_extracts_tvd_only_from_true_vertical_depth_label() -> None:
    record = normalize_record(
        {
            "API": "30-045-35432",
            "Potash Waiver": (
                "No C-129 Incidents: 0 Proposed: 10493 "
                "Measured Vertical Depth: 10470 True Vertical Depth: 5502"
            ),
            "TVD": "",
        }
    )

    assert record["TVD"] == 5502


def test_normalize_record_does_not_use_neighbor_date_for_missing_inspection() -> None:
    record = normalize_record(
        {
            "API": "30-005-00586",
            "Last Inspection": (
                "Current APD Expiration: 01/01/1902 Gas Capture Plan: "
                "TA Expiration: PNR Expiration: Last MIT / BHT:"
            ),
        }
    )

    assert record["Last Inspection"] is None


def test_normalize_records_filters_and_sorts_by_api() -> None:
    records = normalize_records(
        [
            {"API": "30-015-00002", "Current Operator": "B"},
            {"API": "30-015-00001", "Current Operator": "A"},
            {"API": "30-015-00003", "Current Operator": "C"},
        ],
        {"3001500001", "3001500002"},
    )

    assert [record["API"] for record in records] == ["3001500001", "3001500002"]
