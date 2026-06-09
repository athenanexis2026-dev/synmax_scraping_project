"""Command-line entry points for the SynMax take-home project."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.normalize import normalize_records, read_api_numbers, read_source_records
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


if __name__ == "__main__":
    main()
