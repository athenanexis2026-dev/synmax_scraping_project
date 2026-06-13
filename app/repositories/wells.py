"""SQLite database access for creating, loading, and querying normalized well data."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from app.repositories.schema import (
    ASSIGNMENT_COLUMNS,
    CREATE_TABLE_SQL,
    GEO_COORDINATE_COLUMNS,
)

SNAKE_CASE_COLUMN_ALIASES = {
    "Operator": "operator",
    "Status": "status",
    "Well Type": "well_type",
    "Work Type": "work_type",
    "Directional Status": "directional_status",
    "Multi-Lateral": "multi_lateral",
    "Mineral Owner": "mineral_owner",
    "Surface Owner": "surface_owner",
    "Surface Location": "surface_location",
    "GL Elevation": "gl_elevation",
    "KB Elevation": "kb_elevation",
    "DF Elevation": "df_elevation",
    "Single/Multiple Completion": "completion_type",
    "Potash Waiver": "potash_waiver",
    "Spud Date": "spud_date",
    "Last Inspection": "last_inspection",
    "TVD": "tvd",
    "API": "api",
    "Latitude": "latitude",
    "Longitude": "longitude",
    "CRS": "crs",
}


# ============================================================================
# CONNECTION AND SCHEMA SETUP
# ============================================================================
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


def recreate_database(connection: sqlite3.Connection) -> None:
    """Recreate the assignment table from scratch."""

    connection.execute("DROP TABLE IF EXISTS api_well_data")
    initialize_database(connection)


# ============================================================================
# WRITE OPERATIONS
# ============================================================================
def upsert_wells(
    connection: sqlite3.Connection, records: Iterable[Mapping[str, Any]]
) -> int:
    """Insert or replace normalized well records by API number."""

    placeholders = ", ".join("?" for _ in ASSIGNMENT_COLUMNS)
    quoted_columns = ", ".join(f'"{column}"' for column in ASSIGNMENT_COLUMNS)
    update_columns = [column for column in ASSIGNMENT_COLUMNS if column != "API"]
    updates = ", ".join(
        f'"{column}" = excluded."{column}"' for column in update_columns
    )
    sql = f"""
        INSERT INTO api_well_data ({quoted_columns})
        VALUES ({placeholders})
        ON CONFLICT("API") DO UPDATE SET {updates}
    """

    rows = [
        tuple(record.get(column) for column in ASSIGNMENT_COLUMNS) for record in records
    ]
    if not rows:
        return 0

    connection.executemany(sql, rows)
    connection.commit()
    return len(rows)


# ============================================================================
# READ OPERATIONS
# ============================================================================
def get_well(connection: sqlite3.Connection, api_number: str) -> dict[str, Any] | None:
    """Return one well row as a plain dictionary."""

    available_columns = _table_columns(connection)
    select_columns = ", ".join(
        _select_expression(available_columns, column) for column in ASSIGNMENT_COLUMNS
    )
    api_column = _source_column(available_columns, "API")
    row = connection.execute(
        f"SELECT {select_columns} FROM api_well_data WHERE {api_column} = ?",
        (api_number,),
    ).fetchone()
    return dict(row) if row else None


def count_wells(connection: sqlite3.Connection) -> int:
    """Return the number of rows in the well table."""

    row = connection.execute("SELECT COUNT(*) AS count FROM api_well_data").fetchone()
    return int(row["count"])


def iter_wells_in_bounds(
    connection: sqlite3.Connection,
    min_latitude: float,
    max_latitude: float,
    min_longitude: float,
    max_longitude: float,
) -> list[dict[str, Any]]:
    """Return wells with coordinates inside a latitude/longitude bounding box."""

    available_columns = _table_columns(connection)
    api_column = _source_column(available_columns, "API")
    latitude_column = _source_column(available_columns, "Latitude")
    longitude_column = _source_column(available_columns, "Longitude")
    rows = connection.execute(
        f"""
        SELECT {api_column} AS "API",
               {latitude_column} AS "Latitude",
               {longitude_column} AS "Longitude"
        FROM api_well_data
        WHERE {latitude_column} IS NOT NULL
          AND {longitude_column} IS NOT NULL
          AND {latitude_column} BETWEEN ? AND ?
          AND {longitude_column} BETWEEN ? AND ?
        ORDER BY {api_column} ASC
        """,
        (min_latitude, max_latitude, min_longitude, max_longitude),
    ).fetchall()
    return [dict(row) for row in rows]


# ============================================================================
# SCHEMA COMPATIBILITY HELPERS
# ============================================================================
def _table_columns(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("PRAGMA table_info(api_well_data)").fetchall()
    return {str(row["name"]) for row in rows}


def _select_expression(available_columns: set[str], assignment_column: str) -> str:
    source_column = _source_column(available_columns, assignment_column, required=False)
    if source_column is None:
        return f'NULL AS "{assignment_column}"'
    return f'{source_column} AS "{assignment_column}"'


def _source_column(
    available_columns: set[str],
    assignment_column: str,
    *,
    required: bool = True,
) -> str | None:
    if assignment_column in available_columns:
        return f'"{assignment_column}"'

    snake_case_column = SNAKE_CASE_COLUMN_ALIASES[assignment_column]
    if snake_case_column in available_columns:
        return f'"{snake_case_column}"'

    if required:
        raise sqlite3.OperationalError(
            f"api_well_data is missing required column {assignment_column!r}"
        )
    return None
