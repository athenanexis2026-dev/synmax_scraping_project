"""Environment-backed runtime settings."""

from __future__ import annotations

import os
from pathlib import Path

from app.core.exceptions import DatabaseUnavailable


# ============================================================================
# DATABASE SETTINGS
# ============================================================================
def get_database_path() -> Path:
    """Return the database path configured in the environment."""

    try:
        database_path = os.environ["SYNMAX_DATABASE_PATH"]
    except KeyError as error:
        raise DatabaseUnavailable("SYNMAX_DATABASE_PATH must be set") from error
    return Path(database_path).expanduser()

