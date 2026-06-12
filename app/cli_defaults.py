"""Default paths and tuning values used by the SynMax CLI."""

from __future__ import annotations

from pathlib import Path

DEFAULT_API_CSV = Path("data/apis_pythondev_test.csv")
DEFAULT_SCRAPE_OUTPUT_CSV = Path("data/api_well_data_scraped.csv")
DEFAULT_SCRAPE_REPORT_JSON = Path("data/scrape_report.json")
DEFAULT_SCRAPE_CHECKPOINT_JSON = Path("data/scrape_checkpoint.json")
DEFAULT_BROWSER_SESSION_JSON = Path("data/firecrawl_browser_session.json")
DEFAULT_DATABASE = Path("api_well_data.db")
DEFAULT_REQUEST_DELAY_SECONDS = 7.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF_SECONDS = 5.0
DEFAULT_BLOCKED_STOP_THRESHOLD = 3
DEFAULT_BROWSER_TTL_SECONDS = 900
DEFAULT_BROWSER_ACTIVITY_TTL_SECONDS = 900
DEFAULT_BROWSER_WAIT_MS = 5000
