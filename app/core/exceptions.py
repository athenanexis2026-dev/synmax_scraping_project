"""Shared application exceptions."""

from __future__ import annotations


# ============================================================================
# API EXCEPTIONS
# ============================================================================
class DatabaseUnavailable(RuntimeError):
    """Raised when the configured SQLite database cannot be read."""

