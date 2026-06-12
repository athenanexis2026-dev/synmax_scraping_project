"""Well API request validation helpers."""

from __future__ import annotations

from fastapi import HTTPException

from app.api.docs import API_NUMBER_ERROR, API_NUMBER_PATTERN


# ============================================================================
# API NUMBER VALIDATION
# ============================================================================
def normalize_hyphenated_api_number(api_number: str) -> str:
    """Validate a public hyphenated API number and return its digit-only storage key."""

    if not API_NUMBER_PATTERN.fullmatch(api_number):
        raise HTTPException(status_code=422, detail=API_NUMBER_ERROR)
    return api_number.replace("-", "")

