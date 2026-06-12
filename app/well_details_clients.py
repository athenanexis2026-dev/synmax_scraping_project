"""Compatibility facade for Well Details Firecrawl clients."""

from __future__ import annotations

from app.services.well_details.clients import (
    BROWSER_USER_AGENT,
    FIRECRAWL_API_BASE_URL,
    FIRECRAWL_SCRAPE_URL,
    FirecrawlBrowserClient,
    FirecrawlBrowserSessionWellDetailsClient,
    FirecrawlWellDetailsClient,
    OpenRequest,
)


# ============================================================================
# PUBLIC RE-EXPORTS
# ============================================================================
__all__ = [
    "BROWSER_USER_AGENT",
    "FIRECRAWL_API_BASE_URL",
    "FIRECRAWL_SCRAPE_URL",
    "FirecrawlBrowserClient",
    "FirecrawlBrowserSessionWellDetailsClient",
    "FirecrawlWellDetailsClient",
    "OpenRequest",
]
