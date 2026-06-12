"""SQLite connection helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.core.exceptions import DatabaseUnavailable


# ============================================================================
# READ-ONLY CONNECTIONS
# ============================================================================
def connect_readonly(database_path: Path) -> sqlite3.Connection:
    """Open a read-only SQLite connection with rows accessible by column name."""

    try:
        readonly_uri = f"{database_path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(readonly_uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection
    except (OSError, sqlite3.Error) as error:
        raise DatabaseUnavailable(f"Database unavailable: {error}") from error

