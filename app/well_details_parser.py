"""Compatibility facade for Well Details parsing helpers."""

from __future__ import annotations

from app.services.well_details.parser import (
    LABEL_TO_COLUMN,
    SNAPSHOT_SECTION_HEADINGS,
    is_protected_without_data,
    parse_well_details_html,
    text_from_browser_execute_response,
    well_details_snapshot_to_html,
)


# ============================================================================
# PUBLIC RE-EXPORTS
# ============================================================================
__all__ = [
    "LABEL_TO_COLUMN",
    "SNAPSHOT_SECTION_HEADINGS",
    "is_protected_without_data",
    "parse_well_details_html",
    "text_from_browser_execute_response",
    "well_details_snapshot_to_html",
]

