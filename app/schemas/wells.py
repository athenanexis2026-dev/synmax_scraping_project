"""Well API request validation helpers."""

from __future__ import annotations

import re

from fastapi import HTTPException


# ============================================================================
# API NUMBER VALIDATION
# ============================================================================
API_NUMBER_PATTERN_TEXT = r"^(?:\d{10}(?:\d{4})?|\d{2}-\d{3}-\d{5}(?:-\d{4})?)$"
API_NUMBER_PATTERN = re.compile(API_NUMBER_PATTERN_TEXT)
API_NUMBER_ERROR = (
    "api_number must use one of these formats: 30-015-25325, 3001525325, "
    "30-015-45678-0000, or 30015456780000"
)


def normalize_hyphenated_api_number(api_number: str) -> str:
    """Validate a public API number and return its digit-only storage key."""

    if not API_NUMBER_PATTERN.fullmatch(api_number):
        raise HTTPException(status_code=422, detail=API_NUMBER_ERROR)
    return api_number.replace("-", "")
