"""SQLite persistence helpers for well data."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from app.schema import ASSIGNMENT_COLUMNS, GEO_COORDINATE_COLUMNS, CREATE_TABLE_SQL


def connect(database_path: Path | str) -> sqlite3.Connection:
    """Open a SQLite connection with row dictionaries enabled."""

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(connection: sqlite3.Connection) -> None:
    """Create the required table and coordinate index if they do not exist."""

    connection.execute(CREATE_TABLE_SQL)
    connection.execute(GEO_COORDINATE_COLUMNS)
    connection.commit()


def upsert_wells(connection: sqlite3.Connection, records: Iterable[Mapping[str, Any]]) -> int:
    """Insert or replace normalized well records by API number."""

    placeholders = ", ".join("?" for _ in ASSIGNMENT_COLUMNS)
    quoted_columns = ", ".join(f'"{column}"' for column in ASSIGNMENT_COLUMNS)
    update_columns = [column for column in ASSIGNMENT_COLUMNS if column != "API"]
    updates = ", ".join(f'"{column}" = excluded."{column}"' for column in update_columns)
    sql = f"""
        INSERT INTO api_well_data ({quoted_columns})
        VALUES ({placeholders})
        ON CONFLICT("API") DO UPDATE SET {updates}
    """

    rows = [tuple(record.get(column) for column in ASSIGNMENT_COLUMNS) for record in records]
    if not rows:
        return 0

    connection.executemany(sql, rows)
    connection.commit()
    return len(rows)


def get_well(connection: sqlite3.Connection, api_number: str) -> dict[str, Any] | None:
    """Return one well row as a plain dictionary."""

    row = connection.execute(
        'SELECT * FROM api_well_data WHERE "API" = ?',
        (api_number,),
    ).fetchone()
    return dict(row) if row else None
