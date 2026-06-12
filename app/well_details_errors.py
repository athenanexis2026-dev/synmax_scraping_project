"""Compatibility facade for Well Details exception types."""

from __future__ import annotations

from app.services.well_details.errors import (
    FirecrawlBrowserError,
    FirecrawlScrapeError,
    ProtectedPageError,
    WellDetailsError,
    WellDetailsParseError,
)


# ============================================================================
# PUBLIC RE-EXPORTS
# ============================================================================
__all__ = [
    "FirecrawlBrowserError",
    "FirecrawlScrapeError",
    "ProtectedPageError",
    "WellDetailsError",
    "WellDetailsParseError",
]

