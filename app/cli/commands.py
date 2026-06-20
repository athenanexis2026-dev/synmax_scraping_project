"""Command parser and handlers for the SynMax ingestion CLI."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path

from app.repositories.wells import (
    connect,
    initialize_database,
    recreate_database,
    upsert_wells,
)
from app.services.ingestion import ScrapeConfig, scrape_wells
from app.services.well_details.clients import (
    FIRECRAWL_API_BASE_URL,
    FirecrawlBrowserClient,
    FirecrawlBrowserSessionWellDetailsClient,
)
from app.services.well_details.errors import (
    FirecrawlBrowserError,
    FirecrawlScrapeError,
    ProtectedPageError,
    WellDetailsParseError,
)
from app.services.well_details.parser import parse_well_details_html
from app.services.well_details.urls import build_well_details_url
from app.utils.normalize import normalize_records, read_api_numbers, read_source_records


# ============================================================================
# CLI DEFAULTS
# ============================================================================
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
DEFAULT_FAILED_STOP_THRESHOLD = 3
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


# ============================================================================
# CLI SETUP
# ============================================================================
def main() -> None:
    """Parse one CLI command, load local env values, and dispatch to its handler."""

    parser = build_parser()
    args = parser.parse_args()
    load_env_file(args.env_file)
    args.func(args)


def build_parser() -> argparse.ArgumentParser:
    """Build the public SynMax CLI surface used directly and by the Makefile."""

    parser = argparse.ArgumentParser(prog="synmax")
    subparsers = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--env-file",
        default=Path(".env"),
        type=Path,
        help="Local environment file with Firecrawl/API settings",
    )

    _add_scraping_command(subparsers, common)
    _add_browser_session_commands(subparsers, common)
    _add_database_command(subparsers, common)

    return parser


# ============================================================================
# SCRAPING COMMANDS
# ============================================================================
def _add_scraping_command(subparsers, common: argparse.ArgumentParser) -> None:
    scrape = subparsers.add_parser(
        "scrape-wells",
        parents=[common],
        help="Scrape official NM OCD Well Details pages into a normalized CSV",
    )
    _add_scrape_options(scrape)
    scrape.set_defaults(func=scrape_wells_command)

    supervised = subparsers.add_parser(
        "scrape-wells-supervised",
        parents=[common],
        help="Scrape wells and recover from protected-page stops with a supervised session",
    )
    _add_scrape_options(supervised)
    supervised.add_argument(
        "--profile-prefix",
        default=DEFAULT_PROFILE_PREFIX,
        help="Prefix for rotating Firecrawl profiles",
    )
    supervised.add_argument(
        "--initial-profile-number",
        default=DEFAULT_INITIAL_PROFILE_NUMBER,
        type=int,
        help="Profile number to use when NM_OCD_FIRECRAWL_PROFILE is missing",
    )
    supervised.add_argument(
        "--max-session-refreshes",
        default=DEFAULT_MAX_SESSION_REFRESHES,
        type=int,
        help="Maximum protected-page recovery sessions to open",
    )
    supervised.add_argument(
        "--verification-timeout",
        default=DEFAULT_VERIFICATION_TIMEOUT_SECONDS,
        type=float,
        help="Seconds to wait for manual Cloudflare verification",
    )
    supervised.add_argument(
        "--verification-check-interval",
        default=DEFAULT_VERIFICATION_CHECK_INTERVAL_SECONDS,
        type=float,
        help="Seconds between verification checks",
    )
    supervised.set_defaults(func=scrape_wells_supervised_command)


def _add_scrape_options(parser: argparse.ArgumentParser) -> None:
    _add_api_csv_option(parser)
    parser.add_argument(
        "--output-csv",
        default=DEFAULT_SCRAPE_OUTPUT_CSV,
        type=Path,
        help="Normalized scrape output CSV",
    )
    parser.add_argument(
        "--report-json",
        default=DEFAULT_SCRAPE_REPORT_JSON,
        type=Path,
        help="Scrape report JSON path",
    )
    parser.add_argument(
        "--checkpoint-json",
        default=DEFAULT_SCRAPE_CHECKPOINT_JSON,
        type=Path,
        help="Resume checkpoint JSON path",
    )
    _add_browser_session_options(parser)
    parser.add_argument(
        "--request-delay",
        default=None,
        type=float,
        help="Seconds to wait between Well Details requests",
    )
    parser.add_argument(
        "--max-retries",
        default=DEFAULT_MAX_RETRIES,
        type=int,
        help="Retries per API",
    )
    parser.add_argument(
        "--retry-backoff",
        default=DEFAULT_RETRY_BACKOFF_SECONDS,
        type=float,
        help="Base seconds for retry backoff",
    )
    parser.add_argument(
        "--blocked-stop-threshold",
        default=DEFAULT_BLOCKED_STOP_THRESHOLD,
        type=int,
        help="Stop after this many consecutive protected pages",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore an existing scrape checkpoint and start fresh",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Exit successfully even if some APIs were not scraped",
    )


def scrape_wells_command(args: argparse.Namespace) -> None:
    """Scrape the requested Well Details pages and fail unless the scrape is complete."""

    api_key = _required_env("FIRECRAWL_API_KEY")
    config = _scrape_config_from_args(
        args,
        resume=not args.no_resume,
        failed_stop_threshold=DEFAULT_FAILED_STOP_THRESHOLD,
    )
    client = _well_details_client_for_command(args, api_key)

    report = scrape_wells(
        config,
        client,
        progress_callback=_print_supervised_progress,
    )
    _print_scrape_summary(report, args)
    if report.get("stopped_reason"):
        print(report["stopped_reason"])
    if not args.allow_incomplete and report["missing_count"] > 0:
        raise SystemExit(
            "Scrape incomplete. If repeated failed pages triggered protection, "
            "run `make ingest-supervised`; otherwise refresh the Firecrawl "
            "browser session and retry `make ingest`."
        )


def scrape_wells_supervised_command(args: argparse.Namespace) -> None:
    """Run the scraper and recover from protected-page stops with manual verification."""

    api_key = _required_env("FIRECRAWL_API_KEY")
    refresh_count = 0
    first_run = True
    _ensure_active_browser_session(args, api_key)

    while True:
        config = _scrape_config_from_args(
            args,
            resume=True if not first_run else not args.no_resume,
            blocked_stop_threshold=SUPERVISED_BLOCKED_STOP_THRESHOLD,
            failed_stop_threshold=SUPERVISED_FAILED_STOP_THRESHOLD,
            max_retries=SUPERVISED_MAX_RETRIES,
        )
        report = scrape_wells(
            config,
            _well_details_client_for_command(args, api_key),
            progress_callback=_print_supervised_progress,
        )
        _print_scrape_summary(report, args)

        if report["missing_count"] == 0:
            return
        if not _report_stopped_for_recovery(report):
            break
        if refresh_count >= args.max_session_refreshes:
            raise SystemExit(
                "Scrape incomplete after {count} supervised session refreshes. "
                "Last stop: {reason}".format(
                    count=refresh_count,
                    reason=report.get("stopped_reason")
                    or "protected/failed pages returned",
                )
            )

        refresh_count += 1
        verification_api = _verification_api_from_report(report, args.api_csv)
        print(
            "Protected or failed pages detected. Starting supervised recovery "
            f"{refresh_count}/{args.max_session_refreshes}."
        )
        _close_active_browser_session(args.browser_session_json, api_key)
        profile_name = _rotate_firecrawl_profile(
            args.env_file,
            profile_prefix=args.profile_prefix,
            initial_profile_number=args.initial_profile_number,
        )
        try:
            session = _create_browser_session_for_api(
                api_key=api_key,
                profile_name=profile_name,
                api_number=verification_api,
                session_json=args.browser_session_json,
            )
        except FirecrawlBrowserError as error:
            raise SystemExit(_browser_session_error_message(error)) from error
        print("Open this Firecrawl live browser URL and complete Cloudflare if shown:")
        print(session.get("interactiveLiveViewUrl") or session.get("liveViewUrl"))
        _wait_for_profile_verification(
            args,
            api_key=api_key,
            api_number=verification_api,
        )
        print("Verification passed. Resuming scrape from the checkpoint.")
        first_run = False

    if not args.allow_incomplete:
        raise SystemExit(
            "Scrape incomplete and supervised recovery was not available. "
            f"Report: {args.report_json}"
        )


def _scrape_config_from_args(
    args: argparse.Namespace,
    *,
    resume: bool,
    blocked_stop_threshold: int | None = None,
    failed_stop_threshold: int | None = None,
    max_retries: int | None = None,
) -> ScrapeConfig:
    request_delay = args.request_delay
    if request_delay is None:
        request_delay = _env_float(
            "NM_OCD_REQUEST_DELAY_SECONDS",
            DEFAULT_REQUEST_DELAY_SECONDS,
        )

    return ScrapeConfig(
        api_csv=args.api_csv,
        output_csv=args.output_csv,
        report_json=args.report_json,
        checkpoint_json=args.checkpoint_json,
        request_delay_seconds=request_delay,
        max_retries=max_retries if max_retries is not None else args.max_retries,
        retry_backoff_seconds=args.retry_backoff,
        blocked_stop_threshold=(
            blocked_stop_threshold
            if blocked_stop_threshold is not None
            else args.blocked_stop_threshold
        ),
        failed_stop_threshold=failed_stop_threshold,
        resume=resume,
    )


def _print_scrape_summary(report: dict, args: argparse.Namespace) -> None:
    print(
        "Scraped {scraped_count}/{requested_count} wells into {output}. "
        "Report: {report}".format(
            scraped_count=report["scraped_count"],
            requested_count=report["requested_count"],
            output=args.output_csv,
            report=args.report_json,
        )
    )


def _print_supervised_progress(report: dict) -> None:
    print(
        "Progress: {green}{scraped_count}/{requested_count} wells scraped{reset} "
        "{red}{failed_count} failed{reset} "
        "({missing_count} remaining).".format(
            green=TERMINAL_GREEN,
            red=TERMINAL_RED,
            reset=TERMINAL_RESET,
            scraped_count=report["scraped_count"],
            requested_count=report["requested_count"],
            failed_count=report.get("failed_count", 0),
            missing_count=report["missing_count"],
        )
    )


def _browser_session_error_message(error: FirecrawlBrowserError) -> str:
    detail = str(error)
    if "429" in detail or "too many requests" in detail.lower():
        return (
            "Firecrawl rate limited browser session creation (HTTP 429 Too Many Requests). "
            "Wait a few minutes, check your Firecrawl quota, then retry "
            "`make ingest-supervised`. Your scrape checkpoint is preserved."
        )
    return (
        "Could not create a Firecrawl browser session. "
        f"{detail}. Your scrape checkpoint is preserved."
    )


def _report_stopped_for_recovery(report: dict) -> bool:
    return bool(report.get("stopped_reason")) and (
        bool(report.get("blocked_count")) or bool(report.get("failed_count"))
    )


# ============================================================================
# BROWSER SESSION COMMANDS
# ============================================================================
def _add_browser_session_commands(subparsers, common: argparse.ArgumentParser) -> None:
    check_session = subparsers.add_parser(
        "check-session",
        parents=[common],
        help="Scrape one Well Details page to confirm the browser session is verified",
    )
    check_session.add_argument(
        "--api",
        default=None,
        help="API number to check; defaults to the first value in --api-csv",
    )
    _add_api_csv_option(check_session)
    _add_browser_session_options(check_session)
    check_session.set_defaults(func=check_session_command)

    open_session = subparsers.add_parser(
        "open-session",
        parents=[common],
        help="Open a Firecrawl browser session so the persistent profile can be verified",
    )
    open_session.add_argument(
        "--api",
        default=None,
        help="API number to open; defaults to the first value in --api-csv",
    )
    _add_api_csv_option(open_session)
    open_session.add_argument(
        "--session-json",
        default=DEFAULT_BROWSER_SESSION_JSON,
        type=Path,
        help="Where to save the created browser session metadata",
    )
    open_session.add_argument(
        "--ttl", default=None, type=int, help="Browser TTL in seconds"
    )
    open_session.add_argument(
        "--activity-ttl",
        default=None,
        type=int,
        help="Browser inactivity TTL in seconds",
    )
    open_session.set_defaults(func=open_session_command)

    close_session = subparsers.add_parser(
        "close-session",
        parents=[common],
        help="Close the Firecrawl browser session so profile cookies/state are saved",
    )
    close_session.add_argument(
        "--session-json",
        default=DEFAULT_BROWSER_SESSION_JSON,
        type=Path,
        help="Browser session metadata written by open-session",
    )
    close_session.set_defaults(func=close_session_command)


def _add_browser_session_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--browser-session-json",
        default=DEFAULT_BROWSER_SESSION_JSON,
        type=Path,
        help="Active Firecrawl browser session metadata",
    )


def check_session_command(args: argparse.Namespace) -> None:
    """Confirm the active Firecrawl path can reach real Well Details HTML."""

    api_number = _resolve_api_for_session(args.api, args.api_csv)
    client = _well_details_client_for_command(args, _required_env("FIRECRAWL_API_KEY"))
    url = build_well_details_url(api_number)
    try:
        html = client.scrape_html(url)
        record = parse_well_details_html(html, expected_api=api_number)
    except ProtectedPageError as error:
        raise SystemExit(
            f"Browser session is not verified yet for NM OCD pages: {error}. "
            "Run `make open-session`, use the interactive URL, keep it open, "
            "then retry."
        ) from error

    print(
        "Verified Firecrawl browser session for {api}: parsed Operator={operator!r}".format(
            api=record.get("API") or api_number,
            operator=record.get("Operator"),
        )
    )


def open_session_command(args: argparse.Namespace) -> None:
    """Create an interactive Firecrawl browser session for solving protected pages."""

    profile_name = _required_env("NM_OCD_FIRECRAWL_PROFILE")
    api_number = _resolve_api_for_session(args.api, args.api_csv)
    session = _create_browser_session_for_api(
        api_key=_required_env("FIRECRAWL_API_KEY"),
        profile_name=profile_name,
        api_number=api_number,
        session_json=args.session_json,
        ttl_seconds=args.ttl,
        activity_ttl_seconds=args.activity_ttl,
    )

    print(f"Opened Firecrawl browser session for profile {profile_name!r}.")
    print(f"Session saved to {args.session_json}")
    print("Open this interactive URL, complete the official site challenge if shown:")
    print(session.get("interactiveLiveViewUrl") or session.get("liveViewUrl"))
    print(
        "After real well data is visible, keep this session open and run: make check-session"
    )
    print("After make ingest finishes, run: make close-session")


def close_session_command(args: argparse.Namespace) -> None:
    """Close a saved Firecrawl browser session so profile state can be persisted."""

    if not args.session_json.exists():
        raise SystemExit(f"Session file not found: {args.session_json}")

    session = json.loads(args.session_json.read_text(encoding="utf-8"))
    session_id = session.get("id")
    if not session_id:
        raise SystemExit(f"Session file has no id: {args.session_json}")

    client = _firecrawl_browser_client(_required_env("FIRECRAWL_API_KEY"))
    client.close_session(session_id)
    session["closed"] = True
    _write_json(args.session_json, session)
    print(
        f"Closed Firecrawl browser session {session_id}. Profile changes should be saved."
    )


def _active_browser_session_id(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        session = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if session.get("closed"):
        return None
    session_id = session.get("id")
    return session_id if isinstance(session_id, str) and session_id else None


def _create_browser_session_for_api(
    *,
    api_key: str,
    profile_name: str,
    api_number: str,
    session_json: Path,
    ttl_seconds: int | None = None,
    activity_ttl_seconds: int | None = None,
) -> dict:
    """Create, save, and navigate a Firecrawl browser session for one API."""

    url = build_well_details_url(api_number)
    client = _firecrawl_browser_client(api_key)
    session = client.create_session(
        profile_name=profile_name,
        ttl_seconds=ttl_seconds
        or _env_int("NM_OCD_BROWSER_TTL_SECONDS", DEFAULT_BROWSER_TTL_SECONDS),
        activity_ttl_seconds=activity_ttl_seconds
        or _env_int(
            "NM_OCD_BROWSER_ACTIVITY_TTL_SECONDS", DEFAULT_BROWSER_ACTIVITY_TTL_SECONDS
        ),
    )
    session["openedUrl"] = url
    session["profile"] = profile_name
    _write_json(session_json, session)

    # Navigation is best-effort; the live session is still useful if a challenge
    # must be completed by the user before page data is visible.
    try:
        _navigate_browser_session(client, session["id"], url)
    except FirecrawlBrowserError as error:
        print(f"Browser session was created, but automatic navigation failed: {error}")
    return session


def _navigate_browser_session(
    client: FirecrawlBrowserClient,
    session_id: str,
    url: str,
) -> None:
    client.execute_node(session_id, _browser_navigation_script(url))


def _browser_navigation_script(url: str) -> str:
    return (
        f"await page.goto({json.dumps(url)}, {{ waitUntil: 'domcontentloaded' }});\n"
        "await page.waitForTimeout(1000);\n"
        f"{SAFE_INFORMATION_MODAL_SCRIPT}\n"
        "console.log(await page.title());"
    )


def _close_active_browser_session(session_json: Path, api_key: str) -> None:
    if not session_json.exists():
        return

    try:
        session = json.loads(session_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return

    session_id = _active_browser_session_id(session_json)
    if not session_id:
        return

    try:
        _firecrawl_browser_client(api_key).close_session(session_id)
        print(f"Closed stale Firecrawl browser session {session_id}.")
    except FirecrawlBrowserError as error:
        session["closeError"] = str(error)
        print(f"Could not close stale Firecrawl browser session {session_id}: {error}")

    session["closed"] = True
    _write_json(session_json, session)


def _ensure_active_browser_session(args: argparse.Namespace, api_key: str) -> None:
    """Open and verify a browser session before supervised scraping starts."""

    if _active_browser_session_id(args.browser_session_json):
        return

    api_number = _resolve_api_for_session(None, args.api_csv)
    profile_name = _required_env(PROFILE_ENV_KEY)
    try:
        session = _create_browser_session_for_api(
            api_key=api_key,
            profile_name=profile_name,
            api_number=api_number,
            session_json=args.browser_session_json,
        )
    except FirecrawlBrowserError as error:
        raise SystemExit(_browser_session_error_message(error)) from error

    print("Open this Firecrawl live browser URL and complete Cloudflare if shown:")
    print(session.get("interactiveLiveViewUrl") or session.get("liveViewUrl"))
    _wait_for_profile_verification(args, api_key=api_key, api_number=api_number)
    print("Verification passed. Starting scrape.")


def _rotate_firecrawl_profile(
    env_file: Path,
    *,
    profile_prefix: str,
    initial_profile_number: int,
) -> str:
    """Increment NM_OCD_FIRECRAWL_PROFILE in .env and in this process."""

    content = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    lines = content.splitlines(keepends=True)
    assignment = _profile_assignment_pattern()
    new_profile: str | None = None

    for index, line in enumerate(lines):
        line_body = line.rstrip("\r\n")
        newline = line[len(line_body) :]
        match = assignment.match(line_body)
        if not match:
            continue

        current_profile = match.group("value").strip()
        current_number = _profile_number(current_profile, profile_prefix)
        if current_number is None:
            raise SystemExit(
                f"{PROFILE_ENV_KEY} must look like {profile_prefix}N, got {current_profile!r}"
            )

        new_profile = f"{profile_prefix}{current_number + 1}"
        lines[index] = (
            f"{match.group('prefix')}{match.group('quote')}{new_profile}"
            f"{match.group('quote')}{match.group('suffix')}{newline}"
        )
        break

    if new_profile is None:
        new_profile = f"{profile_prefix}{initial_profile_number}"
        content = "".join(lines)
        if content and not content.endswith(("\n", "\r")):
            content += "\n"
        lines = [content, f"{PROFILE_ENV_KEY}={new_profile}\n"]

    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("".join(lines), encoding="utf-8")
    os.environ[PROFILE_ENV_KEY] = new_profile
    print(f"Using Firecrawl profile {new_profile!r}.")
    return new_profile


def _profile_assignment_pattern() -> re.Pattern:
    return re.compile(
        rf"^(?P<prefix>\s*{re.escape(PROFILE_ENV_KEY)}\s*=\s*)"
        r"(?P<quote>[\"']?)(?P<value>.*?)(?P=quote)(?P<suffix>\s*(?:#.*)?)$"
    )


def _profile_number(profile_name: str, profile_prefix: str) -> int | None:
    match = re.fullmatch(rf"{re.escape(profile_prefix)}(?P<number>\d+)", profile_name)
    return int(match.group("number")) if match else None


def _verification_api_from_report(report: dict, api_csv: Path) -> str:
    for key in ("blocked_apis",):
        api_numbers = report.get(key)
        if api_numbers:
            return sorted(str(api_number) for api_number in api_numbers)[0]
    parse_failures = report.get("parse_failures")
    if isinstance(parse_failures, dict) and parse_failures:
        return sorted(str(api_number) for api_number in parse_failures)[0]
    api_numbers = report.get("missing_apis")
    if api_numbers:
        return sorted(str(api_number) for api_number in api_numbers)[0]
    return _resolve_api_for_session(None, api_csv)


def _wait_for_profile_verification(
    args: argparse.Namespace,
    *,
    api_key: str,
    api_number: str,
) -> None:
    deadline = time.monotonic() + max(0.0, args.verification_timeout)
    last_error: BaseException | None = None

    while True:
        try:
            if _session_is_verified(args, api_key=api_key, api_number=api_number):
                return
        except (
            FirecrawlBrowserError,
            FirecrawlScrapeError,
            ProtectedPageError,
            WellDetailsParseError,
            ValueError,
        ) as error:
            last_error = error

        now = time.monotonic()
        if now >= deadline:
            detail = f" Last verification error: {last_error}" if last_error else ""
            raise SystemExit(
                "Timed out waiting for manual Firecrawl/Cloudflare verification."
                f"{detail}"
            )

        wait_seconds = min(args.verification_check_interval, deadline - now)
        print(
            "Waiting for manual verification in the Firecrawl live browser "
            f"({wait_seconds:g}s)..."
        )
        time.sleep(max(0.0, wait_seconds))


def _session_is_verified(
    args: argparse.Namespace, *, api_key: str, api_number: str
) -> bool:
    session_id = _active_browser_session_id(args.browser_session_json)
    if session_id:
        try:
            _firecrawl_browser_client(api_key).execute_node(
                session_id,
                SAFE_INFORMATION_MODAL_SCRIPT,
            )
        except FirecrawlBrowserError:
            pass

    client = _well_details_client_for_command(args, api_key)
    html = client.scrape_html(build_well_details_url(api_number))
    parse_well_details_html(html, expected_api=api_number)
    return True


# ============================================================================
# DATABASE LOADING COMMANDS
# ============================================================================
def _add_database_command(subparsers, common: argparse.ArgumentParser) -> None:
    load_db = subparsers.add_parser(
        "load-db",
        parents=[common],
        help="Load normalized well records into SQLite",
    )
    _add_api_csv_option(load_db)
    load_db.add_argument(
        "--source-csv",
        default=DEFAULT_SCRAPE_OUTPUT_CSV,
        type=Path,
        help="Normalized Well Details scrape CSV",
    )
    load_db.add_argument(
        "--database",
        default=DEFAULT_DATABASE,
        type=Path,
        help="SQLite DB path",
    )
    load_db.add_argument(
        "--replace",
        action="store_true",
        help="Drop and recreate api_well_data before loading",
    )
    load_db.set_defaults(func=load_database_command)


def load_database_command(args: argparse.Namespace) -> None:
    """Normalize scraped records and load them into the api_well_data SQLite table."""

    api_numbers = read_api_numbers(args.api_csv)
    source_records = read_source_records(args.source_csv)
    normalized_records = normalize_records(source_records, api_numbers)

    connection = connect(args.database)
    try:
        if args.replace:
            recreate_database(connection)
        else:
            initialize_database(connection)
        loaded_count = upsert_wells(connection, normalized_records)
    finally:
        connection.close()

    print(f"Loaded {loaded_count} well records into {args.database}")


# ============================================================================
# API NUMBER HELPERS
# ============================================================================
def _add_api_csv_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--api-csv",
        default=DEFAULT_API_CSV,
        type=Path,
        help="CSV containing target API numbers",
    )


def _resolve_api_for_session(api_number: str | None, api_csv: Path) -> str:
    if api_number:
        return api_number
    api_numbers = sorted(read_api_numbers(api_csv))
    if not api_numbers:
        raise SystemExit(f"No API numbers found in {api_csv}")
    return api_numbers[0]


# ============================================================================
# ENVIRONMENT HELPERS
# ============================================================================
def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE pairs from a local env file without overriding the shell."""

    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _env_float(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if not raw_value:
        return default
    try:
        return float(raw_value)
    except ValueError:
        raise SystemExit(f"{name} must be a number, got {raw_value!r}") from None


def _env_int(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    if not raw_value:
        return default
    try:
        return int(raw_value)
    except ValueError:
        raise SystemExit(f"{name} must be an integer, got {raw_value!r}") from None


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(
            f"{name} is required. Add it once to .env, or pass --env-file."
        )
    return value


# ============================================================================
# FIRECRAWL CLIENT HELPERS
# ============================================================================
def _firecrawl_api_base_url() -> str:
    configured = os.environ.get("FIRECRAWL_API_URL")
    if not configured:
        return FIRECRAWL_API_BASE_URL
    configured = configured.rstrip("/")
    if configured.endswith("/v2"):
        return configured
    return configured + "/v2"


def _firecrawl_browser_client(api_key: str) -> FirecrawlBrowserClient:
    return FirecrawlBrowserClient(
        api_key=api_key,
        base_url=_firecrawl_api_base_url(),
    )


def _well_details_client_for_command(args: argparse.Namespace, api_key: str):
    """Build the only supported Well Details client: an active browser session."""

    session_id = _active_browser_session_id(args.browser_session_json)
    if not session_id:
        raise SystemExit(
            "No active Firecrawl browser session found. Run `make open-session`, "
            "complete verification in the live browser, then retry."
        )

    return FirecrawlBrowserSessionWellDetailsClient(
        browser_client=_firecrawl_browser_client(api_key),
        session_id=session_id,
        wait_for_ms=_env_int("NM_OCD_BROWSER_WAIT_MS", DEFAULT_BROWSER_WAIT_MS),
    )


# ============================================================================
# FILE OUTPUT HELPERS
# ============================================================================
def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
