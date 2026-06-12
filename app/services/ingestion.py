"""Checkpointed Well Details scraping pipeline."""

from __future__ import annotations

import csv
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.repositories.schema import ASSIGNMENT_COLUMNS
from app.services.well_details.errors import (
    FirecrawlScrapeError,
    ProtectedPageError,
    WellDetailsParseError,
)
from app.services.well_details.parser import parse_well_details_html
from app.services.well_details.urls import build_well_details_url
from app.utils.normalize import normalize_record, read_api_numbers


class WellDetailsClient(Protocol):
    """Protocol for live and test Well Details clients."""

    def scrape_html(self, url: str) -> str:
        """Return one Well Details page as HTML."""


@dataclass
class ScrapeConfig:
    api_csv: Path
    output_csv: Path
    report_json: Path
    checkpoint_json: Path
    request_delay_seconds: float = 7.0
    max_retries: int = 3
    retry_backoff_seconds: float = 5.0
    blocked_stop_threshold: int = 3
    resume: bool = True


# ============================================================================
# SCRAPER TIMING HELPERS
# ============================================================================
def sleep_with_heartbeat(seconds: float, sleeper: Callable[[float], None] = time.sleep) -> None:
    """Sleep in short beats so scraper pacing is visible and interruptible."""

    remaining = max(0.0, seconds)
    while remaining > 0:
        beat = min(1.0, remaining)
        sleeper(beat)
        remaining -= beat


# ============================================================================
# SCRAPING PIPELINE
# ============================================================================
def scrape_wells(
    config: ScrapeConfig,
    client: WellDetailsClient,
    *,
    sleeper: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Scrape requested APIs, writing CSV, report JSON, and checkpoint JSON."""

    sleeper = sleeper or sleep_with_heartbeat
    api_numbers = sorted(read_api_numbers(config.api_csv))
    checkpoint = _read_checkpoint(config.checkpoint_json) if config.resume else _empty_checkpoint()
    consecutive_blocked = 0
    stopped_reason: str | None = None

    for index, api_number in enumerate(api_numbers):
        if api_number in checkpoint["completed"]:
            continue

        url = build_well_details_url(api_number)
        try:
            record = _scrape_one_api(
                api_number,
                url,
                client,
                config=config,
                sleeper=sleeper,
            )
        except ProtectedPageError as error:
            checkpoint["blocked"][api_number] = {"url": url, "reason": str(error)}
            checkpoint["failures"].pop(api_number, None)
            consecutive_blocked += 1
            if consecutive_blocked >= config.blocked_stop_threshold:
                stopped_reason = (
                    f"Stopped after {consecutive_blocked} consecutive protected pages. "
                    "Refresh the verified Firecrawl session/profile before resuming."
                )
        except (FirecrawlScrapeError, WellDetailsParseError, ValueError) as error:
            checkpoint["failures"][api_number] = {"url": url, "reason": str(error)}
            consecutive_blocked = 0
        else:
            checkpoint["completed"][api_number] = record
            checkpoint["blocked"].pop(api_number, None)
            checkpoint["failures"].pop(api_number, None)
            consecutive_blocked = 0

        _persist_outputs(config, api_numbers, checkpoint, stopped_reason)

        if stopped_reason:
            break
        if index < len(api_numbers) - 1 and config.request_delay_seconds > 0:
            sleeper(config.request_delay_seconds)

    return _persist_outputs(config, api_numbers, checkpoint, stopped_reason)


def _scrape_one_api(
    api_number: str,
    url: str,
    client: WellDetailsClient,
    *,
    config: ScrapeConfig,
    sleeper: Callable[[float], None],
) -> dict[str, Any]:
    last_error: BaseException | None = None
    for attempt in range(1, config.max_retries + 1):
        try:
            html_text = client.scrape_html(url)
            parsed_record = parse_well_details_html(html_text, expected_api=api_number)
            normalized = normalize_record(parsed_record)
            if normalized["API"] is None:
                normalized["API"] = api_number
            return normalized
        except ProtectedPageError:
            raise
        except (FirecrawlScrapeError, WellDetailsParseError, ValueError) as error:
            last_error = error
            if attempt < config.max_retries:
                sleeper(config.retry_backoff_seconds * attempt)

    raise FirecrawlScrapeError(f"Failed after {config.max_retries} attempts: {last_error}")


# ============================================================================
# OUTPUT PERSISTENCE
# ============================================================================
def _persist_outputs(
    config: ScrapeConfig,
    api_numbers: list[str],
    checkpoint: dict[str, Any],
    stopped_reason: str | None,
) -> dict[str, Any]:
    rows = _completed_rows(checkpoint)
    report = _build_report(api_numbers, rows, checkpoint, stopped_reason)
    _write_checkpoint(config.checkpoint_json, checkpoint)
    _write_csv(config.output_csv, rows)
    _write_json(config.report_json, report)
    return report


def _completed_rows(checkpoint: dict[str, Any]) -> list[dict[str, Any]]:
    rows = list(checkpoint["completed"].values())
    return sorted(rows, key=lambda row: row.get("API") or "")


def _build_report(
    api_numbers: list[str],
    rows: list[dict[str, Any]],
    checkpoint: dict[str, Any],
    stopped_reason: str | None,
) -> dict[str, Any]:
    completed_apis = {str(row["API"]) for row in rows if row.get("API")}
    missing_apis = sorted(set(api_numbers) - completed_apis)
    remaining_null_columns = {
        column: count
        for column in ASSIGNMENT_COLUMNS
        if (
            count := sum(
                1
                for row in rows
                if row.get(column) is None or row.get(column) == ""
            )
        )
    }
    return {
        "source": "WellDetails.aspx",
        "requested_count": len(api_numbers),
        "scraped_count": len(rows),
        "blocked_count": len(checkpoint["blocked"]),
        "failed_count": len(checkpoint["failures"]),
        "missing_count": len(missing_apis),
        "missing_apis": missing_apis,
        "blocked_apis": sorted(checkpoint["blocked"]),
        "parse_failures": checkpoint["failures"],
        "blocked_details": checkpoint["blocked"],
        "remaining_null_columns": remaining_null_columns,
        "stopped_reason": stopped_reason,
    }


def _read_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_checkpoint()

    with path.open(encoding="utf-8") as checkpoint_file:
        payload = json.load(checkpoint_file)

    return {
        "completed": dict(payload.get("completed") or {}),
        "blocked": dict(payload.get("blocked") or {}),
        "failures": dict(payload.get("failures") or {}),
    }


def _empty_checkpoint() -> dict[str, Any]:
    return {"completed": {}, "blocked": {}, "failures": {}}


def _write_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    _write_json(path, checkpoint)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=ASSIGNMENT_COLUMNS)
        writer.writeheader()
        writer.writerows(
            {column: row.get(column) for column in ASSIGNMENT_COLUMNS}
            for row in rows
        )
