"""URL helpers for official NM OCD Well Details pages."""

from __future__ import annotations

from typing import Any

from app.utils.normalize import normalize_api_number


# ============================================================================
# CONFIGURATION CONSTANTS
# ============================================================================
WELL_DETAILS_URL_TEMPLATE = (
    "https://wwwapps.emnrd.nm.gov/OCD/OCDPermitting/Data/WellDetails.aspx?api={api}"
)


# ============================================================================
# URL HELPERS
# ============================================================================
def build_well_details_url(api_number: str) -> str:
    """Build the official Well Details URL for a digit-only or hyphenated API."""

    hyphenated = hyphenate_api_number(api_number)
    if hyphenated is None:
        raise ValueError(f"Invalid API number: {api_number!r}")
    return WELL_DETAILS_URL_TEMPLATE.format(api=hyphenated)


def hyphenate_api_number(value: Any) -> str | None:
    """Return NM OCD's public hyphenated API form."""

    digits = normalize_api_number(value)
    if digits is None:
        return None
    if len(digits) == 10:
        return f"{digits[:2]}-{digits[2:5]}-{digits[5:]}"
    if len(digits) == 14:
        return f"{digits[:2]}-{digits[2:5]}-{digits[5:10]}-{digits[10:]}"
    return None
