"""Fetch and parse NM OCD well detail pages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from lxml import html

from app.normalize import normalize_api_number, normalize_record

WELL_DETAILS_BASE_URL = "https://wwwapps.emnrd.nm.gov/OCD/OCDPermitting/Data/WellDetails.aspx"

LABEL_ALIASES = {
    "operator": "Operator",
    "current operator": "Operator",
    "status": "Status",
    "well type": "Well Type",
    "type": "Well Type",
    "work type": "Work Type",
    "direction": "Directional Status",
    "directional status": "Directional Status",
    "multi-lateral": "Multi-Lateral",
    "multi lateral": "Multi-Lateral",
    "mineral owner": "Mineral Owner",
    "surface owner": "Surface Owner",
    "surface location": "Surface Location",
    "gl elevation": "GL Elevation",
    "ground level elevation": "GL Elevation",
    "kb elevation": "KB Elevation",
    "kelly bushing": "KB Elevation",
    "df elevation": "DF Elevation",
    "drilling floor": "DF Elevation",
    "single/multiple completion": "Single/Multiple Completion",
    "single multiple completion": "Single/Multiple Completion",
    "single / multi compl": "Single/Multiple Completion",
    "potash waiver": "Potash Waiver",
    "spud": "Spud Date",
    "spud date": "Spud Date",
    "last inspection": "Last Inspection",
    "tvd": "TVD",
    "true vertical depth": "TVD",
    "api": "API",
    "latitude": "Latitude",
    "longitude": "Longitude",
    "lat / long": "Lat / Long",
    "crs": "CRS",
    "projection": "CRS",
}


class ScraperError(Exception):
    """Base error for scraper failures."""


class HumanVerificationRequired(ScraperError):
    """Raised when the response is a Cloudflare Turnstile gate."""


@dataclass(frozen=True)
class FetchedPage:
    api: str
    url: str
    html: str
    status_code: int


def format_api_for_query(api_number: str) -> str:
    """Format an API number for the NM OCD query string."""

    normalized = normalize_api_number(api_number)
    if normalized is None or len(normalized) != 10:
        raise ValueError(f"Expected a 10-digit API number, got {api_number!r}")
    return f"{normalized[:2]}-{normalized[2:5]}-{normalized[5:]}"


def build_well_details_url(api_number: str) -> str:
    """Build the NM OCD well-detail URL for one API number."""

    query = urlencode({"api": format_api_for_query(api_number)})
    return f"{WELL_DETAILS_BASE_URL}?{query}"


def fetch_well_page(api_number: str, timeout: float = 30.0) -> FetchedPage:
    """Fetch one NM OCD well-detail page."""

    url = build_well_details_url(api_number)
    headers = {
        "User-Agent": "synmax-python-takehome/0.1 (+responsible educational scraper)",
        "Accept": "text/html,application/xhtml+xml",
    }
    with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()

    return FetchedPage(
        api=format_api_for_query(api_number),
        url=str(response.url),
        html=response.text,
        status_code=response.status_code,
    )


def parse_well_details(page_html: str, api_number: str | None = None) -> dict[str, Any]:
    """Parse a well-detail page into normalized assignment columns."""

    if is_human_verification_page(page_html):
        raise HumanVerificationRequired("NM OCD returned a Cloudflare Turnstile verification page")

    raw_values = extract_label_values(page_html)
    if api_number is not None:
        raw_values.setdefault("API", api_number)
    return normalize_record(raw_values)


def is_human_verification_page(page_html: str) -> bool:
    """Return True when the page is a Cloudflare Turnstile verification gate."""

    lowered = page_html.lower()
    return (
        "cf-turnstile" in lowered
        or "cloudflareturnstile" in lowered
        or "verifying you" in lowered
    )


def extract_label_values(page_html: str) -> dict[str, str]:
    """Extract known well fields from common label/value table layouts."""

    document = html.fromstring(page_html)
    extracted: dict[str, str] = {}

    for row in document.xpath(
        "//div[./span[contains(concat(' ', normalize-space(@class), ' '), ' fw-bold ')]]"
    ):
        label_node = row.xpath(
            "./span[contains(concat(' ', normalize-space(@class), ' '), ' fw-bold ')][1]"
        )
        if not label_node:
            continue
        label = _clean_text(label_node[0].text_content())
        value_parts = [
            text
            for text in (
                _clean_text(node.text_content())
                for node in row.xpath(
                    "./span[not(contains(concat(' ', normalize-space(@class), ' '), ' fw-bold '))]"
                )
            )
            if text
        ]
        if label and value_parts:
            _store_if_known(extracted, label, " ".join(value_parts))

    for row in document.xpath(
        "//tr[not(ancestor::table[contains(concat(' ', normalize-space(@class), ' '), ' tblGrid ')])]"
    ):
        cells = [_clean_text(cell.text_content()) for cell in row.xpath("./th|./td")]
        cells = [cell for cell in cells if cell]
        if len(cells) == 2:
            _store_if_known(extracted, cells[0], cells[1])
        elif len(cells) > 2:
            for label, value in zip(cells[0::2], cells[1::2], strict=False):
                _store_if_known(extracted, label, value)

    for definition_list in document.xpath("//dl"):
        terms = [_clean_text(term.text_content()) for term in definition_list.xpath("./dt")]
        descriptions = [_clean_text(dd.text_content()) for dd in definition_list.xpath("./dd")]
        for label, value in zip(terms, descriptions, strict=False):
            if label and value:
                _store_if_known(extracted, label, value)

    return extracted


def _store_if_known(extracted: dict[str, str], label: str, value: str) -> None:
    normalized_label = _normalize_label(label)
    target_field = LABEL_ALIASES.get(normalized_label)
    if not target_field or not value:
        return
    if target_field == "Lat / Long":
        _store_lat_long(extracted, value)
        return
    if extracted.get(target_field):
        return
    extracted[target_field] = _clean_scraped_value(value)


def _store_lat_long(extracted: dict[str, str], value: str) -> None:
    match = re.search(
        r"(?P<lat>-?\d+(?:\.\d+)?)\s*,\s*(?P<long>-?\d+(?:\.\d+)?)(?:\s+(?P<crs>\S+))?",
        value,
    )
    if not match:
        return
    extracted["Latitude"] = match.group("lat")
    extracted["Longitude"] = match.group("long")
    if match.group("crs"):
        extracted["CRS"] = match.group("crs")


def _normalize_label(label: str) -> str:
    label = label.replace("(*)", "")
    label = re.sub(r"[^a-zA-Z0-9/ -]+", " ", label)
    label = re.sub(r"\s+", " ", label)
    return label.strip(" :").lower()


def _clean_text(value: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None


def _clean_scraped_value(value: str) -> str:
    return re.sub(r"^\[\d+\]\s*", "", value).strip()
