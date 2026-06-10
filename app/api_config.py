"""Configuration and API documentation constants for the FastAPI service."""

from __future__ import annotations

import re


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
API_NUMBER_PATTERN_TEXT = r"^\d{2}-\d{3}-\d{5}(?:-\d{4})?$"
API_NUMBER_PATTERN = re.compile(API_NUMBER_PATTERN_TEXT)
API_NUMBER_DESCRIPTION = (
    "Hyphenated New Mexico API number. Use `30-015-25325` for 10-digit APIs or "
    "`30-015-45678-0000` for 14-digit APIs."
)
API_NUMBER_ERROR = (
    "api_number must use a hyphenated format like 30-015-25325 or 30-015-45678-0000"
)
CACHE_CONTROL = "public, max-age=300"
DEFAULT_DATABASE_PATH = "sqlite.db"
DEFAULT_DOTENV_PATH = ".env"
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
