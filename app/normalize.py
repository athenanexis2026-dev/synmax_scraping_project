"""Normalize source records into the assignment's exact column shape."""
"""COMMENT: RETURN TO THIS TO CHECK IF THE SCHEMMA IS CORRECT"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from app.schema import ASSIGNMENT_COLUMNS, INTEGER_COLUMNS, REAL_COLUMNS

FIELD_MAPPING = {
    "Current Operator": "Operator",
    "Status": "Status",
    "Type": "Well Type",
    "Work Type": "Work Type",
    "Mineral Owner": "Mineral Owner",
    "Surface Owner": "Surface Owner",
    "Projection": "CRS",
    "True Vertical Depth": "TVD",
    "Elevation": "GL Elevation",
    "Kelly Bushing": "KB Elevation",
    "Drilling Floor": "DF Elevation",
    "Spud Date": "Spud Date",
    "Last Inspection": "Last Inspection",
    "Latitude": "Latitude",
    "Longitude": "Longitude",
    "API": "API",
}

LOCATION_FIELDS = [
    "Unit Letter",
    "Section",
    "Township",
    "Range",
    "OCD Unit Letter",
    "Footages",
    "Footage NS",
    "NS Indicator",
    "Footage EW",
    "EW Indicator",
]

API_DIGITS = re.compile(r"\d+")


def read_api_numbers(csv_path: Path | str) -> set[str]:
    """Read assignment API numbers from a CSV with either an API column or one value per row."""

    with Path(csv_path).open(newline="", encoding="utf-8-sig") as csv_file:
        sample = csv_file.read(4096)
        csv_file.seek(0)
        has_header = csv.Sniffer().has_header(sample)
        if has_header:
            reader = csv.DictReader(csv_file)
            api_column = _find_api_column(reader.fieldnames or [])
            if api_column is None:
                raise ValueError("API-number CSV must include an API column")
            return {
                normalized
                for row in reader
                if (normalized := normalize_api_number(row.get(api_column)))
            }

        return {
            normalized
            for row in csv.reader(csv_file)
            if row and (normalized := normalize_api_number(row[0]))
        }


def read_source_records(csv_path: Path | str) -> list[dict[str, str]]:
    """Read a source/export CSV into dictionaries."""

    with Path(csv_path).open(newline="", encoding="utf-8-sig") as csv_file:
        return list(csv.DictReader(csv_file))


def normalize_records(
    source_records: Iterable[Mapping[str, Any]],
    api_numbers: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Normalize export/detail records and optionally filter to the requested API numbers."""

    normalized_records = []
    for source_record in source_records:
        record = normalize_record(source_record)
        api_number = record["API"]
        if not api_number:
            continue
        if api_numbers is not None and api_number not in api_numbers:
            continue
        normalized_records.append(record)

    return sorted(normalized_records, key=lambda record: record["API"])


def normalize_record(source_record: Mapping[str, Any]) -> dict[str, Any]:
    """Map one source record into the exact `api_well_data` table columns."""

    record = {column: None for column in ASSIGNMENT_COLUMNS}
    for column in ASSIGNMENT_COLUMNS:
        record[column] = _coerce_value(column, source_record.get(column))

    for source_field, target_field in FIELD_MAPPING.items():
        if record[target_field] is None:
            record[target_field] = _coerce_value(target_field, source_record.get(source_field))

    if record["Surface Location"] is None:
        record["Surface Location"] = build_surface_location(source_record)
    record["API"] = normalize_api_number(record["API"])
    return record


def normalize_api_number(value: Any) -> str | None:
    """Normalize API values to digits only while preserving leading zeroes when present."""

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    digits = "".join(API_DIGITS.findall(text))
    return digits or None


def build_surface_location(source_record: Mapping[str, Any]) -> str | None:
    """Build a compact surface-location string from fields present in the export."""

    parts = []
    for field in LOCATION_FIELDS:
        value = _clean_text(source_record.get(field))
        if value:
            parts.append(f"{field}: {value}")
    return "; ".join(parts) if parts else None


def _find_api_column(fieldnames: list[str]) -> str | None:
    for fieldname in fieldnames:
        normalized = fieldname.strip().lower().replace(" ", "")
        if normalized in {"api", "apinumber", "api#"}:
            return fieldname
    return None


def _coerce_value(column: str, value: Any) -> Any:
    text = _clean_text(value)
    if text is None:
        return None
    if column in INTEGER_COLUMNS:
        return _coerce_int(text)
    if column in REAL_COLUMNS:
        return _coerce_float(text)
    return text


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_int(value: str) -> int | None:
    cleaned = value.replace(",", "")
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def _coerce_float(value: str) -> float | None:
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None
