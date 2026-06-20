"""Default values shared by SynMax CLI commands."""

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
SUPERVISED_BLOCKED_STOP_THRESHOLD = 1
SUPERVISED_FAILED_STOP_THRESHOLD = 1
SUPERVISED_MAX_RETRIES = 1
DEFAULT_BROWSER_TTL_SECONDS = 900
DEFAULT_BROWSER_ACTIVITY_TTL_SECONDS = 900
DEFAULT_BROWSER_WAIT_MS = 5000
DEFAULT_PROFILE_PREFIX = "nm-ocd-verified-"
DEFAULT_INITIAL_PROFILE_NUMBER = 6
DEFAULT_MAX_SESSION_REFRESHES = 5
DEFAULT_VERIFICATION_TIMEOUT_SECONDS = 600.0
DEFAULT_VERIFICATION_CHECK_INTERVAL_SECONDS = 10.0
PROFILE_ENV_KEY = "NM_OCD_FIRECRAWL_PROFILE"
TERMINAL_GREEN = "\033[32m"
TERMINAL_RED = "\033[31m"
TERMINAL_RESET = "\033[0m"
SAFE_INFORMATION_MODAL_SCRIPT = """
await page.evaluate(() => {
  const safeLabels = [/^(close|ok|okay|i understand|got it)$/i];
  const elements = Array.from(
    document.querySelectorAll(
      'button, [role="button"], input[type="button"], input[type="submit"], a'
    )
  );
  const match = elements.find((element) => {
    const label = (
      element.innerText ||
      element.value ||
      element.getAttribute("aria-label") ||
      ""
    ).trim();
    return safeLabels.some((pattern) => pattern.test(label));
  });
  if (match) {
    match.click();
  }
});
await page.waitForTimeout(500);
"""
