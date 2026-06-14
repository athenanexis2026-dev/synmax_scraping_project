import json

import pytest

from app.services.well_details.clients import (
    FirecrawlBrowserSessionWellDetailsClient,
    FirecrawlWellDetailsClient,
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


WELL_DETAILS_HTML = """
<input type="hidden" id="API" value="30-045-35432"/>
<div id="datapane" data-uc="GetWellHeader">
  <div>
    <span class="fw-bold nowrap w-150px">Operator:</span>
    <span class="text-mute ms-1">[<a>371838</a>] DJR OPERATING, LLC</span>
  </div>
  <div class="d-flex">
    <span class="fw-bold nowrap w-150px">Status:</span>
    <span class="text-mute ms-2">Active</span>
  </div>
  <div class="d-flex">
    <span class="fw-bold nowrap w-150px">Well Type:</span>
    <span class="text-mute ms-2">Oil</span>
  </div>
  <div class="d-flex">
    <span class="fw-bold nowrap w-150px">Work Type:</span>
    <span class="text-mute ms-2">New</span>
  </div>
  <div class="d-flex">
    <span class="fw-bold nowrap w-150px">Surface Location:</span>
    <span class="text-mute ms-2">E-07-24N-09W</span>
    <span class="text-mute ps-2">Lot: 2</span>
    <span class="text-mute ps-2">1640 FNL</span>
    <span class="text-mute ps-2">262 FWL</span>
  </div>
  <div class="d-flex">
    <span class="fw-bold nowrap w-150px">Lat / Long:</span>
    <span class="text-mute ms-2">36.3313293,-107.8383865 NAD83</span>
  </div>
  <div class="d-flex">
    <span class="fw-bold nowrap w-150px">GL Elevation:</span>
    <span class="text-mute ms-2">6876</span>
  </div>
  <div class="d-flex">
    <span class="fw-bold nowrap w-150px">KB Elevation:</span>
    <span class="text-mute ms-2"></span>
  </div>
  <div class="d-flex">
    <span class="fw-bold nowrap w-150px">DF Elevation:</span>
    <span class="text-mute ms-2"></span>
  </div>
  <div class="d-flex">
    <span class="fw-bold nowrap w-150px">Direction:</span>
    <span class="text-mute ms-2">Horizontal</span>
  </div>
  <div class="d-flex">
    <span class="fw-bold nowrap w-150px">Multi-Lateral:</span>
    <span class="text-mute ms-2">No</span>
  </div>
  <div class="d-flex">
    <span class="fw-bold nowrap w-150px">Mineral Owner:</span>
    <span class="text-mute ms-2">Federal</span>
  </div>
  <div class="d-flex">
    <span class="fw-bold nowrap w-150px">Surface Owner:</span>
    <span class="text-mute ms-2">Federal</span>
  </div>
  <div class="d-flex">
    <span class="fw-bold nowrap w-150px">Single / Multi Compl:</span>
    <span class="text-mute ms-2">Single</span>
  </div>
  <div class="d-flex">
    <span class="fw-bold nowrap w-150px">Potash Waiver:</span>
    <span class="text-mute ms-2">No</span>
  </div>
  <div class="d-flex">
    <span class="fw-bold nowrap w-150px">Measured Vertical Depth:</span>
    <span class="text-mute ms-2">10470</span>
  </div>
  <div class="d-flex">
    <span class="fw-bold nowrap w-150px">True Vertical Depth:</span>
    <span class="text-mute ms-2">5502</span>
  </div>
  <div class="d-flex">
    <span class="fw-bold nowrap w-150px">Spud:</span>
    <span class="text-mute ms-2">02/27/2014</span>
  </div>
  <div class="d-flex">
    <span class="fw-bold nowrap w-150px">Last Inspection:</span>
    <span class="text-mute ms-2">03/03/2026</span>
  </div>
</div>
"""

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


def test_parse_well_details_html_extracts_assignment_fields() -> None:
    record = normalize_record(parse_well_details_html(WELL_DETAILS_HTML))

    assert record["API"] == "3004535432"
    assert record["Operator"] == "DJR OPERATING, LLC"
    assert record["Status"] == "Active"
    assert record["Well Type"] == "Oil"
    assert record["Work Type"] == "New"
    assert record["Directional Status"] == "Horizontal"
    assert record["Multi-Lateral"] == "No"
    assert record["Mineral Owner"] == "Federal"
    assert record["Surface Owner"] == "Federal"
    assert record["Surface Location"] == "E-07-24N-09W Lot: 2 1640 FNL 262 FWL"
    assert record["GL Elevation"] == 6876
    assert record["KB Elevation"] is None
    assert record["DF Elevation"] is None
    assert record["Single/Multiple Completion"] == "Single"
    assert record["Potash Waiver"] == "No"
    assert record["Spud Date"] == "02/27/2014"
    assert record["Last Inspection"] == "03/03/2026"
    assert record["TVD"] == 5502
    assert record["Latitude"] == 36.3313293
    assert record["Longitude"] == -107.8383865
    assert record["CRS"] == "NAD83"


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


def test_parse_well_details_html_rejects_protected_page_without_data() -> None:
    with pytest.raises(ProtectedPageError):
        parse_well_details_html(
            "<html><script src='https://challenges.cloudflare.com/turnstile/v0/api.js'>"
            "</script><body>Just a moment</body></html>"
        )


def test_parse_well_details_html_rejects_failed_verification_page() -> None:
    with pytest.raises(ProtectedPageError):
        parse_well_details_html(
            "<html><body><h1>Verification Failed</h1>"
            "<p>We could not verify your request through Cloudflare Turnstile.</p>"
            "<p>Please use our official API instead of scraping this page.</p>"
            "</body></html>"
        )


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


def test_firecrawl_client_requests_html_with_profile() -> None:
    captured = {}

    def opener(request, timeout):
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return json.dumps(
            {
                "success": True,
                "data": {"rawHtml": WELL_DETAILS_HTML, "metadata": {"statusCode": 200}},
            }
        ).encode("utf-8")

    client = FirecrawlWellDetailsClient(
        api_key="fc-test",
        profile_name="nm-ocd",
        opener=opener,
    )

    assert client.scrape_html("https://example.test/well") == WELL_DETAILS_HTML
    assert captured["headers"]["Authorization"] == "Bearer fc-test"
    assert captured["payload"]["formats"] == ["html", "rawHtml"]
    assert captured["payload"]["onlyMainContent"] is False
    assert captured["payload"]["profile"] == {"name": "nm-ocd", "saveChanges": True}
    assert captured["payload"]["headers"]["User-Agent"]


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
