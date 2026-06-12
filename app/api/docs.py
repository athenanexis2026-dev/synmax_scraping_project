"""OpenAPI documentation constants for the FastAPI service."""

from __future__ import annotations

import re


# ============================================================================
# APPLICATION METADATA
# ============================================================================
APP_METADATA = {
    "title": "SynMax Well Data API",
    "summary": "Read-only API for New Mexico well records loaded into SQLite.",
    "description": (
        "Serves the `api_well_data` SQLite table through read-only endpoints. "
        "The API accepts hyphenated API numbers publicly and normalizes them "
        "to digit-only keys for database lookup."
    ),
    "openapi_tags": [
        {"name": "health", "description": "Service and database readiness checks."},
        {"name": "wells", "description": "Read-only well data lookup and search."},
    ],
}


# ============================================================================
# WELL ROUTE DOCUMENTATION
# ============================================================================
API_NUMBER_PATTERN_TEXT = r"^\d{2}-\d{3}-\d{5}(?:-\d{4})?$"
API_NUMBER_PATTERN = re.compile(API_NUMBER_PATTERN_TEXT)
API_NUMBER_DESCRIPTION = (
    "Hyphenated New Mexico API number. Use `30-015-25325` for 10-digit APIs or "
    "`30-015-45678-0000` for 14-digit APIs."
)
API_NUMBER_EXAMPLES = ["30-015-25325", "30-015-45678-0000"]
API_NUMBER_ERROR = (
    "api_number must use a hyphenated format like 30-015-25325 or 30-015-45678-0000"
)
WELL_RESPONSE_EXAMPLE = {
    "Operator": "Permian Star Energy",
    "Status": "Active",
    "Well Type": "Oil",
    "Work Type": "New Drill",
    "Directional Status": "Horizontal",
    "Multi-Lateral": "No",
    "Mineral Owner": "Blackstone Minerals",
    "Surface Owner": "Garcia Ranch LLC",
    "Surface Location": "Sec 12 T24S R33E",
    "GL Elevation": 3184.5,
    "KB Elevation": 3206.5,
    "DF Elevation": 3201.2,
    "Single/Multiple Completion": "Single",
    "Potash Waiver": "Yes",
    "Spud Date": "2024-01-15",
    "Last Inspection": "2026-05-20",
    "TVD": 10450.0,
    "API": "30015456780000",
    "Latitude": 32.215647,
    "Longitude": -103.654982,
    "CRS": "EPSG:4326",
}
WELL_ROUTE_RESPONSES = {
    200: {
        "description": "Well found.",
        "content": {"application/json": {"example": WELL_RESPONSE_EXAMPLE}},
    },
    304: {"description": "The cached client copy is still current."},
    404: {"description": "The API number is well-formed but no row exists."},
    422: {"description": "The API number is not hyphenated correctly."},
    503: {"description": "The configured SQLite database is unavailable."},
}


# ============================================================================
# POLYGON ROUTE DOCUMENTATION
# ============================================================================
POLYGON_POINTS_DESCRIPTION = (
    "Ordered polygon vertices as semicolon-separated latitude,longitude pairs. "
    "Example: `32,-105;33,-105;33,-104;32,-104`. At least three distinct points "
    "are required."
)
POLYGON_POINTS_EXAMPLES = [
    "32,-105;33,-105;33,-104;32,-104",
    "32.81,-104.19;32.66,-104.32;32.54,-104.24;32.81,-104.19",
]
POLYGON_RESPONSE_EXAMPLE = {
    "api_numbers": ["30015432100000", "30025411230000"],
    "count": 2,
}
POLYGON_ROUTE_RESPONSES = {
    200: {
        "description": "Polygon search completed.",
        "content": {"application/json": {"example": POLYGON_RESPONSE_EXAMPLE}},
    },
    304: {"description": "The cached client copy is still current."},
    422: {"description": "The polygon points are missing, malformed, or invalid."},
    503: {"description": "The configured SQLite database is unavailable."},
}

