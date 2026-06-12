import csv
import sqlite3
import sys

import app.cli as cli


def test_scrape_command_loads_env_file_and_uses_firecrawl_profile(
    tmp_path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "FIRECRAWL_API_KEY=fc-test",
                "NM_OCD_FIRECRAWL_PROFILE=nm-ocd-test",
                "NM_OCD_REQUEST_DELAY_SECONDS=11",
            ]
        ),
        encoding="utf-8",
    )
    api_csv = tmp_path / "apis.csv"
    api_csv.write_text("api\n30-045-35432\n", encoding="utf-8")
    captured = {}

    class FakeFirecrawlClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

    def fake_scrape_wells(config, client):
        captured["config"] = config
        captured["client"] = client
        return {
            "scraped_count": 1,
            "requested_count": 1,
            "missing_count": 0,
            "stopped_reason": None,
        }

    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("NM_OCD_FIRECRAWL_PROFILE", raising=False)
    monkeypatch.delenv("NM_OCD_REQUEST_DELAY_SECONDS", raising=False)
    monkeypatch.setattr(cli, "FirecrawlWellDetailsClient", FakeFirecrawlClient)
    monkeypatch.setattr(cli, "scrape_wells", fake_scrape_wells)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "synmax",
            "scrape-wells",
            "--env-file",
            str(env_file),
            "--api-csv",
            str(api_csv),
            "--output-csv",
            str(tmp_path / "wells.csv"),
            "--report-json",
            str(tmp_path / "report.json"),
            "--checkpoint-json",
            str(tmp_path / "checkpoint.json"),
            "--no-browser-session",
        ],
    )

    cli.main()

    assert captured["client_kwargs"]["api_key"] == "fc-test"
    assert captured["client_kwargs"]["profile_name"] == "nm-ocd-test"
    assert captured["config"].request_delay_seconds == 11
    assert captured["config"].api_csv == api_csv


def test_open_session_command_writes_session_file_and_prints_interactive_url(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "FIRECRAWL_API_KEY=fc-test",
                "NM_OCD_FIRECRAWL_PROFILE=nm-ocd-test",
            ]
        ),
        encoding="utf-8",
    )
    api_csv = tmp_path / "apis.csv"
    api_csv.write_text("api\n30-045-35432\n", encoding="utf-8")
    session_json = tmp_path / "session.json"
    captured = {}

    class FakeBrowserClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        def create_session(self, **kwargs):
            captured["create_kwargs"] = kwargs
            return {
                "success": True,
                "id": "browser-1",
                "interactiveLiveViewUrl": "https://liveview.test/interactive",
            }

        def execute_node(self, session_id, code):
            captured["execute"] = {"session_id": session_id, "code": code}
            return {"success": True}

    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("NM_OCD_FIRECRAWL_PROFILE", raising=False)
    monkeypatch.setattr(cli, "FirecrawlBrowserClient", FakeBrowserClient)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "synmax",
            "open-session",
            "--env-file",
            str(env_file),
            "--api-csv",
            str(api_csv),
            "--session-json",
            str(session_json),
        ],
    )

    cli.main()

    assert captured["client_kwargs"]["api_key"] == "fc-test"
    assert captured["create_kwargs"]["profile_name"] == "nm-ocd-test"
    assert captured["execute"]["session_id"] == "browser-1"
    assert "30-045-35432" in captured["execute"]["code"]
    assert "https://liveview.test/interactive" in capsys.readouterr().out
    assert '"id": "browser-1"' in session_json.read_text(encoding="utf-8")


def test_close_session_command_closes_saved_browser_session(
    tmp_path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FIRECRAWL_API_KEY=fc-test\n", encoding="utf-8")
    session_json = tmp_path / "session.json"
    session_json.write_text('{"id": "browser-1"}', encoding="utf-8")
    captured = {}

    class FakeBrowserClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        def close_session(self, session_id):
            captured["closed"] = session_id
            return {"success": True}

    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.setattr(cli, "FirecrawlBrowserClient", FakeBrowserClient)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "synmax",
            "close-session",
            "--env-file",
            str(env_file),
            "--session-json",
            str(session_json),
        ],
    )

    cli.main()

    assert captured["client_kwargs"]["api_key"] == "fc-test"
    assert captured["closed"] == "browser-1"
    assert '"closed": true' in session_json.read_text(encoding="utf-8")


def test_load_db_command_replaces_schema_and_loads_scraped_rows(tmp_path, monkeypatch) -> None:
    api_csv = tmp_path / "apis.csv"
    source_csv = tmp_path / "wells.csv"
    database = tmp_path / "api_well_data.db"
    api_csv.write_text("api\n30-045-35432\n", encoding="utf-8")
    with source_csv.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["API", "Operator", "Latitude", "Longitude"])
        writer.writeheader()
        writer.writerow(
            {
                "API": "30-045-35432",
                "Operator": "DJR OPERATING, LLC",
                "Latitude": "36.3313293",
                "Longitude": "-107.8383865",
            }
        )

    connection = sqlite3.connect(database)
    try:
        connection.execute('CREATE TABLE api_well_data ("API" TEXT, old_column TEXT)')
        connection.commit()
    finally:
        connection.close()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "synmax",
            "load-db",
            "--env-file",
            str(tmp_path / "missing.env"),
            "--api-csv",
            str(api_csv),
            "--source-csv",
            str(source_csv),
            "--database",
            str(database),
            "--replace",
        ],
    )

    cli.main()

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(api_well_data)").fetchall()
        }
        row = connection.execute(
            'SELECT "API", "Operator", "Latitude", "Longitude" FROM api_well_data'
        ).fetchone()
    finally:
        connection.close()

    assert "old_column" not in columns
    assert row["API"] == "3004535432"
    assert row["Operator"] == "DJR OPERATING, LLC"
    assert row["Latitude"] == 36.3313293
    assert row["Longitude"] == -107.8383865
