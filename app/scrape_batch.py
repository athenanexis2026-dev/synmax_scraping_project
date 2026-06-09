"""Batch scraping workflow for NM OCD well detail pages."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx

from app.normalize import normalize_api_number, read_api_numbers
from app.scraper import (
    HumanVerificationRequired,
    fetch_well_page,
    format_api_for_query,
    parse_well_details,
)

ScrapeStatus = Literal["scraped", "cached", "gated", "error"]


@dataclass(frozen=True)
class ScrapeResult:
    api: str
    status: ScrapeStatus
    record: dict[str, Any] | None = None
    cache_path: str | None = None
    error: str | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "api": self.api,
                "status": self.status,
                "record": self.record,
                "cache_path": self.cache_path,
                "error": self.error,
            },
            sort_keys=True,
        )


def scrape_api_file(
    api_csv: Path,
    cache_dir: Path,
    report_path: Path,
    delay_seconds: float = 0.5,
    limit: int | None = None,
) -> list[ScrapeResult]:
    """Scrape API numbers from a CSV and write a JSONL result report."""

    api_numbers = sorted(read_api_numbers(api_csv))
    if limit is not None:
        api_numbers = api_numbers[:limit]

    cache_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    results = []
    with report_path.open("w", encoding="utf-8") as report_file:
        for index, api_number in enumerate(api_numbers):
            result = scrape_one_api(api_number, cache_dir)
            results.append(result)
            report_file.write(result.to_json() + "\n")
            report_file.flush()

            if delay_seconds > 0 and index < len(api_numbers) - 1:
                time.sleep(delay_seconds)

    return results


def scrape_one_api(api_number: str, cache_dir: Path) -> ScrapeResult:
    """Scrape or parse one API number using the local cache when available."""

    normalized_api = normalize_api_number(api_number)
    if normalized_api is None:
        return ScrapeResult(api=str(api_number), status="error", error="Invalid API number")

    cache_path = cache_dir / f"{normalized_api}.html"
    if cache_path.exists():
        return parse_cached_html(normalized_api, cache_path)

    try:
        page = fetch_well_page(normalized_api)
        cache_path.write_text(page.html, encoding="utf-8")
        record = parse_well_details(page.html, normalized_api)
    except HumanVerificationRequired as error:
        return ScrapeResult(
            api=format_api_for_query(normalized_api),
            status="gated",
            cache_path=str(cache_path),
            error=str(error),
        )
    except (httpx.HTTPError, OSError, ValueError) as error:
        return ScrapeResult(api=normalized_api, status="error", error=str(error))

    return ScrapeResult(
        api=format_api_for_query(normalized_api),
        status="scraped",
        record=record,
        cache_path=str(cache_path),
    )


def parse_cached_html(api_number: str, cache_path: Path) -> ScrapeResult:
    """Parse one cached HTML page."""

    try:
        page_html = cache_path.read_text(encoding="utf-8")
        record = parse_well_details(page_html, api_number)
    except HumanVerificationRequired as error:
        return ScrapeResult(
            api=format_api_for_query(api_number),
            status="gated",
            cache_path=str(cache_path),
            error=str(error),
        )
    except (OSError, ValueError) as error:
        return ScrapeResult(
            api=format_api_for_query(api_number),
            status="error",
            cache_path=str(cache_path),
            error=str(error),
        )

    return ScrapeResult(
        api=format_api_for_query(api_number),
        status="cached",
        record=record,
        cache_path=str(cache_path),
    )


def summarize_results(results: list[ScrapeResult]) -> dict[str, int]:
    """Count scrape results by status."""

    summary = {"scraped": 0, "cached": 0, "gated": 0, "error": 0}
    for result in results:
        summary[result.status] += 1
    return summary
