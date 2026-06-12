"""Compatibility facade for NM OCD Well Details fetching and parsing helpers."""

from __future__ import annotations

from app.scrape_timing import sleep_with_heartbeat
from app.well_details_clients import (
    BROWSER_USER_AGENT,
    FIRECRAWL_API_BASE_URL,
    FIRECRAWL_SCRAPE_URL,
    FirecrawlBrowserClient,
    FirecrawlBrowserSessionWellDetailsClient,
    FirecrawlWellDetailsClient,
    OpenRequest,
)
from app.well_details_errors import (
    FirecrawlBrowserError,
    FirecrawlScrapeError,
    ProtectedPageError,
    WellDetailsError,
    WellDetailsParseError,
)
from app.well_details_parser import (
    is_protected_without_data,
    parse_well_details_html,
    well_details_snapshot_to_html,
)
from app.well_details_urls import (
    WELL_DETAILS_URL_TEMPLATE,
    build_well_details_url,
    hyphenate_api_number,
)


# ============================================================================
# PUBLIC RE-EXPORTS
# ============================================================================
__all__ = [
    "BROWSER_USER_AGENT",
    "FIRECRAWL_API_BASE_URL",
    "FIRECRAWL_SCRAPE_URL",
    "WELL_DETAILS_URL_TEMPLATE",
    "FirecrawlBrowserClient",
    "FirecrawlBrowserError",
    "FirecrawlBrowserSessionWellDetailsClient",
    "FirecrawlScrapeError",
    "FirecrawlWellDetailsClient",
    "OpenRequest",
    "ProtectedPageError",
    "WellDetailsError",
    "WellDetailsParseError",
    "build_well_details_url",
    "hyphenate_api_number",
    "is_protected_without_data",
    "parse_well_details_html",
    "sleep_with_heartbeat",
    "well_details_snapshot_to_html",
]
