import pytest

from app.services.well_details.clients import (
    FirecrawlBrowserSessionWellDetailsClient,
)
from app.services.well_details.errors import ProtectedPageError
from app.services.well_details.parser import (
    parse_well_details_html,
    well_details_snapshot_to_html,
)
from app.services.well_details.urls import (
    build_well_details_url,
    hyphenate_api_number,
)
from app.utils.normalize import normalize_record


WELL_DETAILS_SNAPSHOT = """
  - main
    - heading "30-005-00586 SOUTH CAPROCK QUEEN UNIT #001 [11446]" [level=1]
    - heading "General Well Information" [level=2]
    - StaticText "Operator:"
    - StaticText "["
    - link "23710" [ref=e43]
    - StaticText "] UNION OIL CO OF CALIFORNIA"
    - StaticText "Status:"
    - StaticText "Plugged, Site Released"
    - StaticText "Well Type:"
    - StaticText "Injection"
    - StaticText "Work Type:"
    - StaticText "New"
    - StaticText "Surface Location:"
    - StaticText "A-07-15S-31E"
    - StaticText "990 FNL"
    - StaticText "450 FEL"
    - StaticText "Lat / Long:"
    - StaticText "33.0349884,-103.854126 NAD83"
    - StaticText "GL Elevation:"
    - StaticText "KB Elevation:"
    - StaticText "DF Elevation:"
    - StaticText "Direction:"
    - StaticText "Multi-Lateral:"
    - StaticText "No"
    - StaticText "Mineral Owner:"
    - StaticText "Surface Owner:"
    - StaticText "Private"
    - StaticText "Single / Multi Compl:"
    - StaticText "Potash Waiver:"
    - StaticText "No"
    - heading "Depths" [level=3]
    - StaticText "True Vertical Depth:"
    - StaticText "3150"
    - heading "Event Dates" [level=3]
    - StaticText "Spud:"
    - StaticText "01/01/1900"
    - StaticText "Last Inspection:"
    - heading "History" [level=3]
"""


def test_parse_well_details_browser_snapshot_extracts_assignment_fields() -> None:
    html = well_details_snapshot_to_html(WELL_DETAILS_SNAPSHOT)
    record = normalize_record(parse_well_details_html(html))

    assert record["API"] == "3000500586"
    assert record["Operator"] == "UNION OIL CO OF CALIFORNIA"
    assert record["Status"] == "Plugged, Site Released"
    assert record["Well Type"] == "Injection"
    assert record["Work Type"] == "New"
    assert record["Surface Location"] == "A-07-15S-31E 990 FNL 450 FEL"
    assert record["Multi-Lateral"] == "No"
    assert record["Surface Owner"] == "Private"
    assert record["Potash Waiver"] == "No"
    assert record["TVD"] == 3150
    assert record["Latitude"] == 33.0349884
    assert record["Longitude"] == -103.854126
    assert record["CRS"] == "NAD83"


def test_parse_well_details_browser_snapshot_stops_at_neighbor_labels() -> None:
    snapshot = """
      - main
        - heading "30-005-00863 SAMPLE WELL #001" [level=1]
        - heading "General Well Information" [level=2]
        - StaticText "Operator:"
        - StaticText "["
        - link "12345" [ref=e43]
        - StaticText "] CELERO ENERGY II, LP"
        - StaticText "Status:"
        - StaticText "Plugged, Site Released"
        - StaticText "Potash Waiver:"
        - StaticText "No"
        - StaticText "C-129 Incidents:"
        - StaticText "0"
        - heading "Proposed Formation and/or Notes" [level=3]
        - StaticText "PA 11/09/2010 BLM"
        - heading "Depths" [level=3]
        - StaticText "Proposed:"
        - StaticText "3059"
        - StaticText "Measured Vertical Depth:"
        - StaticText "3059"
        - heading "Event Dates" [level=3]
        - StaticText "Spud:"
        - StaticText "11/09/2010"
        - StaticText "Approved TA:"
        - StaticText "Shut In:"
        - StaticText "Plug & Abandoned Intent:"
        - StaticText "Well Plugged:"
        - StaticText "11/09/2010"
        - StaticText "Last Inspection:"
        - StaticText "06/03/2009"
        - StaticText "Current APD Expiration:"
        - StaticText "01/01/1902"
        - heading "History" [level=3]
    """

    html = well_details_snapshot_to_html(snapshot)
    record = normalize_record(parse_well_details_html(html))

    assert record["API"] == "3000500863"
    assert record["Potash Waiver"] == "No"
    assert record["TVD"] is None
    assert record["Spud Date"] == "11/09/2010"
    assert record["Last Inspection"] == "06/03/2009"


def test_parse_well_details_browser_snapshot_rejects_protected_page() -> None:
    with pytest.raises(ProtectedPageError):
        well_details_snapshot_to_html(
            '- Iframe "Widget containing a Cloudflare security challenge"\n'
            '- StaticText "Verify you are human"\n'
        )


def test_hyphenate_api_number_and_build_url() -> None:
    assert hyphenate_api_number("3004535432") == "30-045-35432"
    assert hyphenate_api_number("30045354320000") == "30-045-35432-0000"
    assert build_well_details_url("3004535432").endswith("?api=30-045-35432")


def test_browser_session_client_uses_agent_browser_snapshot() -> None:
    captured = {}

    class FakeBrowserClient:
        def execute_bash(self, session_id, code):
            captured["session_id"] = session_id
            captured["code"] = code
            return {"success": True, "stdout": WELL_DETAILS_SNAPSHOT}

    client = FirecrawlBrowserSessionWellDetailsClient(
        browser_client=FakeBrowserClient(),
        session_id="browser-1",
        wait_for_ms=2500,
    )

    html = client.scrape_html("https://example.test/well?api=30-005-00586")

    assert captured["session_id"] == "browser-1"
    assert "agent-browser open" in captured["code"]
    assert "sleep 2.5" in captured["code"]
    assert parse_well_details_html(html)["Operator"] == "UNION OIL CO OF CALIFORNIA"
