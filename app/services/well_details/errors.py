"""Exception types for NM OCD Well Details fetching and parsing."""

from __future__ import annotations


# ============================================================================
# ERROR TYPES
# ============================================================================
class WellDetailsError(RuntimeError):
    """Base error for Well Details ingestion."""


class FirecrawlScrapeError(WellDetailsError):
    """Raised when Firecrawl cannot return page HTML."""


class FirecrawlBrowserError(WellDetailsError):
    """Raised when a Firecrawl browser session operation fails."""


class ProtectedPageError(WellDetailsError):
    """Raised when the official page returns only a protection/challenge page."""


class WellDetailsParseError(WellDetailsError):
    """Raised when a Well Details page cannot be parsed into well fields."""

