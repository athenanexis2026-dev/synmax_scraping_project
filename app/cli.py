"""Command-line entry points for the SynMax take-home project."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.normalize import normalize_records, read_api_numbers, read_source_records
from app.scrape_batch import scrape_api_file, summarize_results
from app.scraper import HumanVerificationRequired, fetch_well_page, parse_well_details
from app.storage import connect, initialize_database, upsert_wells


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="synmax")
    subparsers = parser.add_subparsers(dest="command", required=True)

    load_db = subparsers.add_parser("load-db", help="Load normalized well records into SQLite")
    load_db.add_argument(
        "--api-csv",
        required=True,
        type=Path,
        help="CSV containing target API numbers",
    )
    load_db.add_argument(
        "--source-csv",
        required=True,
        type=Path,
        help="Expanded export/source CSV",
    )
    load_db.add_argument("--database", default=Path("sqlite.db"), type=Path, help="SQLite DB path")
    load_db.set_defaults(func=load_database_command)

    scrape_one = subparsers.add_parser("scrape-one", help="Fetch and parse one NM OCD well page")
    scrape_one.add_argument("api", help="API number to scrape, e.g. 30-045-35432")
    scrape_one.set_defaults(func=scrape_one_command)

    parse_html = subparsers.add_parser("parse-html", help="Parse a saved NM OCD well HTML file")
    parse_html.add_argument("html_file", type=Path, help="Saved verified WellDetails HTML file")
    parse_html.add_argument("--api", help="API number for the saved page")
    parse_html.set_defaults(func=parse_html_command)

    scrape_batch = subparsers.add_parser(
        "scrape-batch",
        help="Fetch/cache NM OCD well pages for API numbers and write a JSONL report",
    )
    scrape_batch.add_argument("--api-csv", required=True, type=Path, help="CSV of API numbers")
    scrape_batch.add_argument(
        "--cache-dir",
        default=Path("data/cache/well_pages"),
        type=Path,
        help="Directory for cached WellDetails HTML",
    )
    scrape_batch.add_argument(
        "--report",
        default=Path("data/scrape_report.jsonl"),
        type=Path,
        help="JSONL report path",
    )
    scrape_batch.add_argument(
        "--delay",
        default=0.5,
        type=float,
        help="Delay in seconds between live requests",
    )
    scrape_batch.add_argument("--limit", type=int, help="Limit APIs for a small test run")
    scrape_batch.set_defaults(func=scrape_batch_command)

    return parser


def load_database_command(args: argparse.Namespace) -> None:
    api_numbers = read_api_numbers(args.api_csv)
    source_records = read_source_records(args.source_csv)
    normalized_records = normalize_records(source_records, api_numbers)

    connection = connect(args.database)
    try:
        initialize_database(connection)
        loaded_count = upsert_wells(connection, normalized_records)
    finally:
        connection.close()

    print(f"Loaded {loaded_count} well records into {args.database}")


def scrape_one_command(args: argparse.Namespace) -> None:
    page = fetch_well_page(args.api)
    try:
        record = parse_well_details(page.html, args.api)
    except HumanVerificationRequired as error:
        print(f"Could not scrape {page.api}: {error}")
        print(f"URL: {page.url}")
        return

    print(json.dumps(record, indent=2, sort_keys=True))


def parse_html_command(args: argparse.Namespace) -> None:
    page_html = args.html_file.read_text(encoding="utf-8")
    record = parse_well_details(page_html, args.api)
    print(json.dumps(record, indent=2, sort_keys=True))


def scrape_batch_command(args: argparse.Namespace) -> None:
    results = scrape_api_file(
        api_csv=args.api_csv,
        cache_dir=args.cache_dir,
        report_path=args.report,
        delay_seconds=args.delay,
        limit=args.limit,
    )
    print(json.dumps(summarize_results(results), indent=2, sort_keys=True))
    print(f"Report written to {args.report}")


if __name__ == "__main__":
    main()
