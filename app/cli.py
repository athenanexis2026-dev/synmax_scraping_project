"""Command-line entry points for the SynMax take-home project."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.config.cli import (
    DEFAULT_API_CSV,
    DEFAULT_BLOCKED_STOP_THRESHOLD,
    DEFAULT_BROWSER_ACTIVITY_TTL_SECONDS,
    DEFAULT_BROWSER_SESSION_JSON,
    DEFAULT_BROWSER_TTL_SECONDS,
    DEFAULT_BROWSER_WAIT_MS,
    DEFAULT_DATABASE,
    DEFAULT_MAX_RETRIES,
    DEFAULT_REQUEST_DELAY_SECONDS,
    DEFAULT_RETRY_BACKOFF_SECONDS,
    DEFAULT_SCRAPE_CHECKPOINT_JSON,
    DEFAULT_SCRAPE_OUTPUT_CSV,
    DEFAULT_SCRAPE_REPORT_JSON,
)
from app.repositories.wells import connect, initialize_database, recreate_database, upsert_wells
from app.services.ingestion import ScrapeConfig, scrape_wells
from app.services.well_details import (
    FIRECRAWL_API_BASE_URL,
    FIRECRAWL_SCRAPE_URL,
    FirecrawlBrowserClient,
    FirecrawlBrowserError,
    FirecrawlBrowserSessionWellDetailsClient,
    FirecrawlWellDetailsClient,
    ProtectedPageError,
    build_well_details_url,
    parse_well_details_html,
)
from app.utils.normalize import normalize_records, read_api_numbers, read_source_records


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
    _add_api_csv_option(scrape)
    scrape.add_argument(
        "--output-csv",
        default=DEFAULT_SCRAPE_OUTPUT_CSV,
        type=Path,
        help="Normalized scrape output CSV",
    )
    scrape.add_argument(
        "--report-json",
        default=DEFAULT_SCRAPE_REPORT_JSON,
        type=Path,
        help="Scrape report JSON path",
    )
    scrape.add_argument(
        "--checkpoint-json",
        default=DEFAULT_SCRAPE_CHECKPOINT_JSON,
        type=Path,
        help="Resume checkpoint JSON path",
    )
    _add_browser_session_options(scrape)
    scrape.add_argument(
        "--request-delay",
        default=None,
        type=float,
        help="Seconds to wait between Well Details requests",
    )
    scrape.add_argument(
        "--max-retries",
        default=DEFAULT_MAX_RETRIES,
        type=int,
        help="Retries per API",
    )
    scrape.add_argument(
        "--retry-backoff",
        default=DEFAULT_RETRY_BACKOFF_SECONDS,
        type=float,
        help="Base seconds for retry backoff",
    )
    scrape.add_argument(
        "--blocked-stop-threshold",
        default=DEFAULT_BLOCKED_STOP_THRESHOLD,
        type=int,
        help="Stop after this many consecutive protected pages",
    )
    scrape.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore an existing scrape checkpoint and start fresh",
    )
    scrape.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Exit successfully even if some APIs were not scraped",
    )
    scrape.set_defaults(func=scrape_wells_command)


def scrape_wells_command(args: argparse.Namespace) -> None:
    """Scrape the requested Well Details pages and fail unless the scrape is complete."""

    api_key = _required_env("FIRECRAWL_API_KEY")

    request_delay = args.request_delay
    if request_delay is None:
        request_delay = _env_float(
            "NM_OCD_REQUEST_DELAY_SECONDS",
            DEFAULT_REQUEST_DELAY_SECONDS,
        )

    config = ScrapeConfig(
        api_csv=args.api_csv,
        output_csv=args.output_csv,
        report_json=args.report_json,
        checkpoint_json=args.checkpoint_json,
        request_delay_seconds=request_delay,
        max_retries=args.max_retries,
        retry_backoff_seconds=args.retry_backoff,
        blocked_stop_threshold=args.blocked_stop_threshold,
        resume=not args.no_resume,
    )
    client = _well_details_client_for_command(args, api_key)

    report = scrape_wells(config, client)
    print(
        "Scraped {scraped_count}/{requested_count} wells into {output}. "
        "Report: {report}".format(
            scraped_count=report["scraped_count"],
            requested_count=report["requested_count"],
            output=args.output_csv,
            report=args.report_json,
        )
    )
    if report.get("stopped_reason"):
        print(report["stopped_reason"])
    if not args.allow_incomplete and report["missing_count"] > 0:
        raise SystemExit(
            "Scrape incomplete. Run `make open-session`, verify the page, "
            "then `make close-session` and retry `make ingest`."
        )


# ============================================================================
# BROWSER SESSION COMMANDS
# ============================================================================
def _add_browser_session_commands(subparsers, common: argparse.ArgumentParser) -> None:
    check_session = subparsers.add_parser(
        "check-session",
        parents=[common],
        help="Scrape one Well Details page to confirm the Firecrawl profile is verified",
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
    open_session.add_argument("--ttl", default=None, type=int, help="Browser TTL in seconds")
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
        help="Use this active Firecrawl browser session before falling back to /scrape",
    )
    parser.add_argument(
        "--no-browser-session",
        action="store_true",
        help="Ignore any active Firecrawl browser session file",
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
            f"Profile is not verified yet for NM OCD pages: {error}. "
            "Run `make open-session`, use the interactive URL, then `make close-session`."
        ) from error

    print(
        "Verified Firecrawl profile for {api}: parsed Operator={operator!r}".format(
            api=record.get("API") or api_number,
            operator=record.get("Operator"),
        )
    )


def open_session_command(args: argparse.Namespace) -> None:
    """Create an interactive Firecrawl browser session for solving protected pages."""

    profile_name = _required_env("NM_OCD_FIRECRAWL_PROFILE")
    api_number = _resolve_api_for_session(args.api, args.api_csv)
    url = build_well_details_url(api_number)
    client = _firecrawl_browser_client(_required_env("FIRECRAWL_API_KEY"))

    session = client.create_session(
        profile_name=profile_name,
        ttl_seconds=args.ttl
        or _env_int("NM_OCD_BROWSER_TTL_SECONDS", DEFAULT_BROWSER_TTL_SECONDS),
        activity_ttl_seconds=args.activity_ttl
        or _env_int("NM_OCD_BROWSER_ACTIVITY_TTL_SECONDS", DEFAULT_BROWSER_ACTIVITY_TTL_SECONDS),
    )
    session["openedUrl"] = url
    session["profile"] = profile_name
    _write_json(args.session_json, session)

    # Navigate the remote browser before handing the live URL to the user. If this
    # fails, the session is still usable for manual challenge completion.
    try:
        client.execute_node(
            session["id"],
            "await page.goto(%r, { waitUntil: 'domcontentloaded' });\n"
            "await page.waitForTimeout(1000);\n"
            "console.log(await page.title());" % url,
        )
    except FirecrawlBrowserError as error:
        print(f"Browser session was created, but automatic navigation failed: {error}")

    print(f"Opened Firecrawl browser session for profile {profile_name!r}.")
    print(f"Session saved to {args.session_json}")
    print("Open this interactive URL, complete the official site challenge if shown:")
    print(session.get("interactiveLiveViewUrl") or session.get("liveViewUrl"))
    print("After real well data is visible, keep this session open and run: make check-session")
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
    print(f"Closed Firecrawl browser session {session_id}. Profile changes should be saved.")


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
        raise SystemExit(f"{name} is required. Add it once to .env, or pass --env-file.")
    return value


# ============================================================================
# FIRECRAWL CLIENT HELPERS
# ============================================================================
def _firecrawl_endpoint() -> str:
    configured = os.environ.get("FIRECRAWL_API_URL")
    if not configured:
        return FIRECRAWL_SCRAPE_URL
    if configured.rstrip("/").endswith("/scrape"):
        return configured
    return configured.rstrip("/") + "/v2/scrape"


def _firecrawl_api_base_url() -> str:
    configured = os.environ.get("FIRECRAWL_API_URL")
    if not configured:
        return FIRECRAWL_API_BASE_URL
    configured = configured.rstrip("/")
    if configured.endswith("/scrape"):
        return configured.rsplit("/", 2)[0]
    if configured.endswith("/v2"):
        return configured
    return configured + "/v2"


def _firecrawl_browser_client(api_key: str) -> FirecrawlBrowserClient:
    return FirecrawlBrowserClient(
        api_key=api_key,
        base_url=_firecrawl_api_base_url(),
    )


def _well_details_client_for_command(args: argparse.Namespace, api_key: str):
    """Prefer a live browser session, then fall back to Firecrawl's scrape endpoint."""

    if not getattr(args, "no_browser_session", False):
        session_id = _active_browser_session_id(args.browser_session_json)
        if session_id:
            return FirecrawlBrowserSessionWellDetailsClient(
                browser_client=_firecrawl_browser_client(api_key),
                session_id=session_id,
                wait_for_ms=_env_int("NM_OCD_BROWSER_WAIT_MS", DEFAULT_BROWSER_WAIT_MS),
            )

    return FirecrawlWellDetailsClient(
        api_key=api_key,
        profile_name=os.environ.get("NM_OCD_FIRECRAWL_PROFILE") or None,
        endpoint=_firecrawl_endpoint(),
        proxy=os.environ.get("NM_OCD_FIRECRAWL_PROXY", "auto"),
    )


# ============================================================================
# FILE OUTPUT HELPERS
# ============================================================================
def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
