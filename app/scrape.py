"""Compatibility facade for the Well Details ingestion service."""

from __future__ import annotations

from app.services.ingestion import ScrapeConfig, WellDetailsClient, scrape_wells


# ============================================================================
# PUBLIC RE-EXPORTS
# ============================================================================
__all__ = ["ScrapeConfig", "WellDetailsClient", "scrape_wells"]

