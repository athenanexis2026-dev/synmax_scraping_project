"""Timing helpers for intentionally paced scraping workflows."""

from __future__ import annotations

import time
from collections.abc import Callable


# ============================================================================
# SCRAPER TIMING HELPERS
# ============================================================================
def sleep_with_heartbeat(seconds: float, sleeper: Callable[[float], None] = time.sleep) -> None:
    """Sleep in short beats so a user can see the scraper is intentionally pacing itself."""

    remaining = max(0.0, seconds)
    while remaining > 0:
        beat = min(1.0, remaining)
        sleeper(beat)
        remaining -= beat
