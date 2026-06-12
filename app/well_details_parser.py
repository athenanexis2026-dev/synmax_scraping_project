"""Parse NM OCD Well Details HTML and browser snapshots into assignment fields."""

from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from typing import Any

from app.well_details_errors import ProtectedPageError, WellDetailsParseError


# ============================================================================
# PARSER CONFIGURATION
# ============================================================================
LABEL_TO_COLUMN = {
    "Operator": "Operator",
    "Status": "Status",
    "Well Type": "Well Type",
    "Work Type": "Work Type",
    "Direction": "Directional Status",
    "Multi-Lateral": "Multi-Lateral",
    "Mineral Owner": "Mineral Owner",
    "Surface Owner": "Surface Owner",
    "Surface Location": "Surface Location",
    "GL Elevation": "GL Elevation",
    "KB Elevation": "KB Elevation",
    "DF Elevation": "DF Elevation",
    "Single / Multi Compl": "Single/Multiple Completion",
    "Potash Waiver": "Potash Waiver",
    "Spud": "Spud Date",
    "Last Inspection": "Last Inspection",
    "True Vertical Depth": "TVD",
}

SNAPSHOT_SECTION_HEADINGS = {
    "Proposed Formation and/or Notes",
    "Depths",
    "Event Dates",
}


# ============================================================================
# WELL DETAILS PARSING
# ============================================================================
def parse_well_details_html(html_text: str, *, expected_api: str | None = None) -> dict[str, Any]:
    """Parse the assignment fields from a Well Details page."""

    if is_protected_without_data(html_text):
        raise ProtectedPageError("Well Details page returned protection content without data")

    label_values = _LabelValueParser.parse(html_text)
    if "Operator" not in label_values and "Status" not in label_values:
        raise WellDetailsParseError("Well Details labels were not found")

    record: dict[str, Any] = {}
    for label, target_column in LABEL_TO_COLUMN.items():
        value = label_values.get(label)
        if value is not None:
            record[target_column] = value

    operator = record.get("Operator")
    if isinstance(operator, str):
        record["Operator"] = _strip_leading_code(operator)

    lat_long = label_values.get("Lat / Long")
    if lat_long:
        latitude, longitude, crs = _parse_lat_long(lat_long)
        record["Latitude"] = latitude
        record["Longitude"] = longitude
        if crs:
            record["CRS"] = crs

    api = _extract_api(html_text) or expected_api
    if api:
        record["API"] = api

    return record


def well_details_snapshot_to_html(snapshot: str) -> str:
    """Convert an agent-browser accessibility snapshot into parser-friendly HTML."""

    if _snapshot_is_protected(snapshot):
        raise ProtectedPageError("Well Details page returned protection content without data")

    label_values = _snapshot_label_values(snapshot)
    if "Operator" not in label_values and "Status" not in label_values:
        raise WellDetailsParseError("Well Details labels were not found in browser snapshot")

    api = _extract_api(snapshot)
    pieces = ["<div id='datapane'>"]
    if api:
        pieces.append(f"<input type='hidden' id='API' value='{html.escape(api)}'/>")
    for label, values in label_values.items():
        value = " ".join(values)
        pieces.append("<div class='d-flex'>")
        pieces.append(f"<span class='fw-bold'>{html.escape(label)}:</span>")
        pieces.append(f"<span class='text-mute'>{html.escape(value)}</span>")
        pieces.append("</div>")
    pieces.append("</div>")
    return "".join(pieces)


def is_protected_without_data(html_text: str) -> bool:
    """Return True when protection/challenge markup is present but well data is absent."""

    lowered = html_text.lower()
    has_data = 'id="datapane"' in lowered or "general well information" in lowered
    has_protection = (
        "challenges.cloudflare.com" in lowered
        or "cf-turnstile" in lowered
        or "cloudflareturnstile" in lowered
        or "just a moment" in lowered
    )
    return has_protection and not has_data


# ============================================================================
# HTML LABEL PARSER
# ============================================================================
class _LabelValueParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._span_roles: list[str | None] = []
        self._label_depth = 0
        self._value_depth = 0
        self._current_label_chunks: list[str] = []
        self._pending_label: str | None = None
        self.values: dict[str, list[str]] = {}

    @classmethod
    def parse(cls, html_text: str) -> dict[str, str]:
        parser = cls()
        parser.feed(html_text)
        values = {}
        for label, parts in parser.values.items():
            value = _clean_text(" ".join(parts))
            if value is not None:
                values[label] = value
        return values

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "span":
            return

        classes = _classes(attrs)
        role: str | None = None
        if "fw-bold" in classes:
            role = "label"
            self._label_depth += 1
            self._current_label_chunks = []
        elif "text-mute" in classes:
            role = "value"
            self._value_depth += 1
        self._span_roles.append(role)

    def handle_endtag(self, tag: str) -> None:
        if tag != "span" or not self._span_roles:
            return

        role = self._span_roles.pop()
        if role == "label":
            self._label_depth -= 1
            label = _normalize_label("".join(self._current_label_chunks))
            if label:
                self._pending_label = label
                self.values.setdefault(label, [])
            self._current_label_chunks = []
        elif role == "value":
            self._value_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._label_depth > 0:
            self._current_label_chunks.append(data)
        elif self._value_depth > 0 and self._pending_label:
            self.values.setdefault(self._pending_label, []).append(data)


# ============================================================================
# TEXT PARSING HELPERS
# ============================================================================
def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
    for name, value in attrs:
        if name == "class" and value:
            return set(value.split())
    return set()


def _normalize_label(value: str) -> str | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    return cleaned.rstrip(":").strip()


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = html.unescape(str(value))
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _strip_leading_code(value: str) -> str:
    return re.sub(r"^\[\s*\d+\s*\]\s*", "", value).strip()


def _parse_lat_long(value: str) -> tuple[str | None, str | None, str | None]:
    match = re.search(
        r"(?P<latitude>[-+]?\d+(?:\.\d+)?)\s*,\s*"
        r"(?P<longitude>[-+]?\d+(?:\.\d+)?)(?:\s+(?P<crs>.+))?",
        value,
    )
    if not match:
        return None, None, None
    return match.group("latitude"), match.group("longitude"), _clean_text(match.group("crs"))


def _extract_api(html_text: str) -> str | None:
    input_match = re.search(
        r'id=["\']API["\'][^>]*\bvalue=["\'](?P<api>[^"\']+)["\']',
        html_text,
        flags=re.IGNORECASE,
    )
    if input_match:
        return input_match.group("api")

    title_match = re.search(r"\b\d{2}-\d{3}-\d{5}(?:-\d{4})?\b", html_text)
    return title_match.group(0) if title_match else None


# ============================================================================
# BROWSER SNAPSHOT HELPERS
# ============================================================================
def text_from_browser_execute_response(response: dict[str, Any]) -> str | None:
    for key in ("stdout", "result"):
        value = response.get(key)
        if isinstance(value, str) and value.strip():
            return value

    data = response.get("data")
    if isinstance(data, dict):
        return text_from_browser_execute_response(data)
    return None


def _snapshot_is_protected(snapshot: str) -> bool:
    lowered = snapshot.lower()
    has_data = "general well information" in lowered and "operator:" in lowered
    has_protection = (
        "cloudflare security challenge" in lowered
        or "verify you are human" in lowered
        or "verifying you" in lowered
        or "turnstile" in lowered
    )
    return has_protection and not has_data


def _snapshot_label_values(snapshot: str) -> dict[str, list[str]]:
    texts = _snapshot_visible_texts(snapshot)
    started = False
    current_label: str | None = None
    label_values: dict[str, list[str]] = {}
    allowed_labels = set(LABEL_TO_COLUMN) | {"Lat / Long"}

    for text in texts:
        normalized = _normalize_label(text)
        if text == "General Well Information":
            started = True
            continue
        if not started:
            continue
        if text == "History":
            break
        if text in SNAPSHOT_SECTION_HEADINGS:
            continue
        if normalized in allowed_labels:
            current_label = normalized
            label_values.setdefault(current_label, [])
            continue
        if current_label and text not in {"`"}:
            label_values[current_label].append(text)

    return label_values


def _snapshot_visible_texts(snapshot: str) -> list[str]:
    texts: list[str] = []
    for line in snapshot.splitlines():
        match = re.search(r'- (?:StaticText|heading|link) "((?:[^"\\]|\\.)*)"', line)
        if not match:
            continue
        try:
            text = json.loads(f'"{match.group(1)}"')
        except json.JSONDecodeError:
            text = match.group(1)
        text = _clean_text(text)
        if text:
            texts.append(text)
    return texts
