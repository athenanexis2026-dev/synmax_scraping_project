"""Compatibility facade for database schema constants."""

from __future__ import annotations

from app.repositories.schema import (
    ASSIGNMENT_COLUMNS,
    CREATE_TABLE_SQL,
    GEO_COORDINATE_COLUMNS,
    INTEGER_COLUMNS,
    REAL_COLUMNS,
)


# ============================================================================
# PUBLIC RE-EXPORTS
# ============================================================================
__all__ = [
    "ASSIGNMENT_COLUMNS",
    "CREATE_TABLE_SQL",
    "GEO_COORDINATE_COLUMNS",
    "INTEGER_COLUMNS",
    "REAL_COLUMNS",
]

