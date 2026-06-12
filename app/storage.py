"""Compatibility facade for well-data repository helpers."""

from __future__ import annotations

from app.repositories.wells import (
    SNAKE_CASE_COLUMN_ALIASES,
    connect,
    count_wells,
    get_well,
    initialize_database,
    iter_wells_in_bounds,
    recreate_database,
    upsert_wells,
)


# ============================================================================
# PUBLIC RE-EXPORTS
# ============================================================================
__all__ = [
    "SNAKE_CASE_COLUMN_ALIASES",
    "connect",
    "count_wells",
    "get_well",
    "initialize_database",
    "iter_wells_in_bounds",
    "recreate_database",
    "upsert_wells",
]

