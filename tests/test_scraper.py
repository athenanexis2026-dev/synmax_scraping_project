import pytest

from app.scraper import (
    HumanVerificationRequired,
    build_well_details_url,
    extract_label_values,
    format_api_for_query,
    is_human_verification_page,
    parse_well_details,
)


def test_format_api_for_query_accepts_hyphenated_or_digits() -> None:
    assert format_api_for_query("30-045-35432") == "30-045-35432"
    assert format_api_for_query("3004535432") == "30-045-35432"


def test_build_well_details_url() -> None:
    assert build_well_details_url("3004535432").endswith(
        "/WellDetails.aspx?api=30-045-35432"
    )


def test_detects_human_verification_page() -> None:
    page_html = '<div class="cf-turnstile"></div><p>Verifying you’re human…</p>'

    assert is_human_verification_page(page_html)
    with pytest.raises(HumanVerificationRequired):
        parse_well_details(page_html, "30-045-35432")


def test_extract_label_values_from_table_pairs() -> None:
    page_html = """
    <table>
      <tr><th>Operator:</th><td>Example Operator</td></tr>
      <tr><td>Status</td><td>Active</td><td>Well Type</td><td>Oil</td></tr>
      <tr><td>True Vertical Depth (*)</td><td>10,250</td></tr>
      <tr><td>Projection (*)</td><td>NAD83</td></tr>
    </table>
    """

    assert extract_label_values(page_html) == {
        "Operator": "Example Operator",
        "Status": "Active",
        "Well Type": "Oil",
        "TVD": "10,250",
        "CRS": "NAD83",
    }


def test_parse_well_details_returns_normalized_assignment_shape() -> None:
    page_html = """
    <table>
      <tr><th>Operator</th><td>Example Operator</td></tr>
      <tr><th>Latitude</th><td>32.75</td></tr>
      <tr><th>Longitude</th><td>-104.05</td></tr>
      <tr><th>TVD</th><td>10,250</td></tr>
    </table>
    """

    record = parse_well_details(page_html, "30-045-35432")

    assert record["API"] == "3004535432"
    assert record["Operator"] == "Example Operator"
    assert record["Latitude"] == 32.75
    assert record["Longitude"] == -104.05
    assert record["TVD"] == 10250


def test_parse_verified_nm_ocd_detail_html() -> None:
    page_html = """
    <input type="hidden" id="API" value="30-045-35432"/>
    <div id="datapane" data-uc="GetWellHeader">
      <div>
        <span class="fw-bold nowrap w-150px">Operator:</span>
        <span class="text-mute ms-1">[371838] DJR OPERATING, LLC</span>
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
      <table class="tblGrid js-sort" summary="Well History">
        <thead>
          <tr>
            <th>Effective Date</th>
            <th>Property</th>
            <th>Well Number</th>
            <th>Operator</th>
            <th>C-101 Work Type</th>
            <th>Well Type</th>
            <th>Well Status</th>
          </tr>
        </thead>
      </table>
    </div>
    """

    record = parse_well_details(page_html, "30-045-35432")

    assert record["Operator"] == "DJR OPERATING, LLC"
    assert record["Status"] == "Active"
    assert record["Well Type"] == "Oil"
    assert record["Work Type"] == "New"
    assert record["Surface Location"] == "E-07-24N-09W Lot: 2 1640 FNL 262 FWL"
    assert record["Latitude"] == 36.3313293
    assert record["Longitude"] == -107.8383865
    assert record["CRS"] == "NAD83"
    assert record["GL Elevation"] == 6876
    assert record["Directional Status"] == "Horizontal"
    assert record["Multi-Lateral"] == "No"
    assert record["Mineral Owner"] == "Federal"
    assert record["Surface Owner"] == "Federal"
    assert record["Single/Multiple Completion"] == "Single"
    assert record["Potash Waiver"] == "No"
    assert record["TVD"] == 5502
    assert record["Spud Date"] == "02/27/2014"
    assert record["Last Inspection"] == "03/03/2026"
