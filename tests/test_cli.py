import csv
import os
import sqlite3
import sys
from pathlib import Path

import pytest

import app.cli as cli
import app.cli.commands as cli_commands

API_NUMBER = "30-045-35432"


def test_scrape_command_loads_env_file_and_uses_firecrawl_profile(
    tmp_path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    _write_env_file(
        env_file,
        FIRECRAWL_API_KEY="fc-test",
        NM_OCD_FIRECRAWL_PROFILE="nm-ocd-test",
        NM_OCD_REQUEST_DELAY_SECONDS="11",
    )
    api_csv = _write_api_csv(tmp_path)
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
    monkeypatch.setattr(cli_commands, "FirecrawlWellDetailsClient", FakeFirecrawlClient)
    monkeypatch.setattr(cli_commands, "scrape_wells", fake_scrape_wells)
    _set_cli_args(
        monkeypatch,
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
    _write_env_file(
        env_file,
        FIRECRAWL_API_KEY="fc-test",
        NM_OCD_FIRECRAWL_PROFILE="nm-ocd-test",
    )
    api_csv = _write_api_csv(tmp_path)
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
    monkeypatch.setattr(cli_commands, "FirecrawlBrowserClient", FakeBrowserClient)
    _set_cli_args(
        monkeypatch,
        "open-session",
        "--env-file",
        str(env_file),
        "--api-csv",
        str(api_csv),
        "--session-json",
        str(session_json),
    )

    cli.main()

    assert captured["client_kwargs"]["api_key"] == "fc-test"
    assert captured["create_kwargs"]["profile_name"] == "nm-ocd-test"
    assert captured["execute"]["session_id"] == "browser-1"
    assert API_NUMBER in captured["execute"]["code"]
    assert "https://liveview.test/interactive" in capsys.readouterr().out
    assert '"id": "browser-1"' in session_json.read_text(encoding="utf-8")


def test_close_session_command_closes_saved_browser_session(
    tmp_path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    _write_env_file(env_file, FIRECRAWL_API_KEY="fc-test")
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
    monkeypatch.setattr(cli_commands, "FirecrawlBrowserClient", FakeBrowserClient)
    _set_cli_args(
        monkeypatch,
        "close-session",
        "--env-file",
        str(env_file),
        "--session-json",
        str(session_json),
    )

    cli.main()

    assert captured["client_kwargs"]["api_key"] == "fc-test"
    assert captured["closed"] == "browser-1"
    assert '"closed": true' in session_json.read_text(encoding="utf-8")


def test_rotate_firecrawl_profile_increments_env_file_and_process_env(
    tmp_path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "FIRECRAWL_API_KEY=fc-test\n"
        "NM_OCD_FIRECRAWL_PROFILE=nm-ocd-verified-6 # keep this\n"
        "OTHER=value\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("NM_OCD_FIRECRAWL_PROFILE", raising=False)

    profile = cli_commands._rotate_firecrawl_profile(
        env_file,
        profile_prefix="nm-ocd-verified-",
        initial_profile_number=6,
    )

    assert profile == "nm-ocd-verified-7"
    assert os.environ["NM_OCD_FIRECRAWL_PROFILE"] == "nm-ocd-verified-7"
    assert env_file.read_text(encoding="utf-8") == (
        "FIRECRAWL_API_KEY=fc-test\n"
        "NM_OCD_FIRECRAWL_PROFILE=nm-ocd-verified-7 # keep this\n"
        "OTHER=value\n"
    )

    profile = cli_commands._rotate_firecrawl_profile(
        env_file,
        profile_prefix="nm-ocd-verified-",
        initial_profile_number=6,
    )

    assert profile == "nm-ocd-verified-8"
    assert (
        "NM_OCD_FIRECRAWL_PROFILE=nm-ocd-verified-8 # keep this"
        in env_file.read_text(encoding="utf-8")
    )


def test_rotate_firecrawl_profile_appends_initial_when_missing(
    tmp_path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FIRECRAWL_API_KEY=fc-test", encoding="utf-8")
    monkeypatch.delenv("NM_OCD_FIRECRAWL_PROFILE", raising=False)

    profile = cli_commands._rotate_firecrawl_profile(
        env_file,
        profile_prefix="nm-ocd-verified-",
        initial_profile_number=6,
    )

    assert profile == "nm-ocd-verified-6"
    assert os.environ["NM_OCD_FIRECRAWL_PROFILE"] == "nm-ocd-verified-6"
    assert env_file.read_text(encoding="utf-8") == (
        "FIRECRAWL_API_KEY=fc-test\nNM_OCD_FIRECRAWL_PROFILE=nm-ocd-verified-6\n"
    )


def test_scrape_wells_supervised_rotates_profile_opens_session_and_resumes(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    env_file = tmp_path / ".env"
    _write_env_file(
        env_file,
        FIRECRAWL_API_KEY="fc-test",
        NM_OCD_FIRECRAWL_PROFILE="nm-ocd-verified-6",
    )
    api_csv = _write_api_csv(tmp_path)
    session_json = tmp_path / "session.json"
    session_json.write_text('{"id": "browser-old"}', encoding="utf-8")
    reports = [
        _protected_report(),
        {
            "scraped_count": 1,
            "requested_count": 1,
            "missing_count": 0,
            "blocked_count": 0,
            "stopped_reason": None,
        },
    ]
    captured = {"configs": [], "events": []}

    class FakeBrowserClient:
        def __init__(self, **kwargs):
            captured["events"].append(("client", kwargs["api_key"]))

        def close_session(self, session_id):
            captured["events"].append(("close", session_id))
            return {"success": True}

        def create_session(self, **kwargs):
            captured["events"].append(("create", kwargs["profile_name"]))
            return {
                "success": True,
                "id": "browser-new",
                "interactiveLiveViewUrl": "https://liveview.test/new",
            }

        def execute_node(self, session_id, code):
            captured["events"].append(("execute", session_id, code))
            return {"success": True}

    def fake_scrape_wells(config, client, *, progress_callback=None):
        captured["configs"].append(config)
        report = reports.pop(0)
        if progress_callback is not None:
            progress_callback(report)
        return report

    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("NM_OCD_FIRECRAWL_PROFILE", raising=False)
    monkeypatch.setattr(cli_commands, "FirecrawlBrowserClient", FakeBrowserClient)
    monkeypatch.setattr(cli_commands, "scrape_wells", fake_scrape_wells)
    monkeypatch.setattr(
        cli_commands, "_session_is_verified", lambda *args, **kwargs: True
    )
    _set_cli_args(
        monkeypatch,
        "scrape-wells-supervised",
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
        "--browser-session-json",
        str(session_json),
        "--max-session-refreshes",
        "1",
    )

    cli.main()

    assert [config.resume for config in captured["configs"]] == [True, True]
    assert [config.blocked_stop_threshold for config in captured["configs"]] == [1, 1]
    assert [config.failed_stop_threshold for config in captured["configs"]] == [1, 1]
    assert [config.max_retries for config in captured["configs"]] == [1, 1]
    assert ("close", "browser-old") in captured["events"]
    assert ("create", "nm-ocd-verified-7") in captured["events"]
    assert os.environ["NM_OCD_FIRECRAWL_PROFILE"] == "nm-ocd-verified-7"
    assert "NM_OCD_FIRECRAWL_PROFILE=nm-ocd-verified-7" in env_file.read_text(
        encoding="utf-8"
    )
    assert '"id": "browser-new"' in session_json.read_text(encoding="utf-8")
    output = capsys.readouterr().out
    assert "\033[32m1/1 wells scraped\033[0m" in output
    assert "\033[31m0 failed\033[0m" in output


def test_scrape_wells_supervised_recovers_after_failed_page(
    tmp_path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    _write_env_file(
        env_file,
        FIRECRAWL_API_KEY="fc-test",
        NM_OCD_FIRECRAWL_PROFILE="nm-ocd-verified-6",
    )
    api_csv = _write_api_csv(tmp_path)
    session_json = tmp_path / "session.json"
    session_json.write_text('{"id": "browser-old"}', encoding="utf-8")
    reports = [
        _failed_report(),
        {
            "scraped_count": 1,
            "requested_count": 1,
            "missing_count": 0,
            "blocked_count": 0,
            "failed_count": 0,
            "stopped_reason": None,
        },
    ]
    captured = {"events": []}

    class FakeBrowserClient:
        def __init__(self, **kwargs):
            pass

        def close_session(self, session_id):
            captured["events"].append(("close", session_id))
            return {"success": True}

        def create_session(self, **kwargs):
            captured["events"].append(("create", kwargs["profile_name"]))
            return {
                "success": True,
                "id": "browser-new",
                "interactiveLiveViewUrl": "https://liveview.test/new",
            }

        def execute_node(self, session_id, code):
            captured["events"].append(("execute", session_id, code))
            return {"success": True}

    def fake_scrape_wells(config, client, *, progress_callback=None):
        return reports.pop(0)

    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("NM_OCD_FIRECRAWL_PROFILE", raising=False)
    monkeypatch.setattr(cli_commands, "FirecrawlBrowserClient", FakeBrowserClient)
    monkeypatch.setattr(cli_commands, "scrape_wells", fake_scrape_wells)
    monkeypatch.setattr(
        cli_commands, "_session_is_verified", lambda *args, **kwargs: True
    )
    _set_cli_args(
        monkeypatch,
        "scrape-wells-supervised",
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
        "--browser-session-json",
        str(session_json),
        "--max-session-refreshes",
        "1",
    )

    cli.main()

    assert ("close", "browser-old") in captured["events"]
    assert ("create", "nm-ocd-verified-7") in captured["events"]


def test_scrape_wells_supervised_exits_cleanly_when_firecrawl_rate_limits_session(
    tmp_path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    _write_env_file(
        env_file,
        FIRECRAWL_API_KEY="fc-test",
        NM_OCD_FIRECRAWL_PROFILE="nm-ocd-verified-6",
    )
    api_csv = _write_api_csv(tmp_path)

    class RateLimitedBrowserClient:
        def __init__(self, **kwargs):
            pass

        def create_session(self, **kwargs):
            raise cli_commands.FirecrawlBrowserError(
                "Firecrawl browser operation failed: HTTP Error 429: Too Many Requests"
            )

    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("NM_OCD_FIRECRAWL_PROFILE", raising=False)
    monkeypatch.setattr(
        cli_commands, "FirecrawlBrowserClient", RateLimitedBrowserClient
    )
    monkeypatch.setattr(
        cli_commands,
        "scrape_wells",
        lambda config, client, **kwargs: _protected_report(),
    )
    _set_cli_args(
        monkeypatch,
        "scrape-wells-supervised",
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
        "--browser-session-json",
        str(tmp_path / "session.json"),
    )

    with pytest.raises(SystemExit, match="Firecrawl rate limited"):
        cli.main()


def test_scrape_wells_supervised_times_out_waiting_for_verification(
    tmp_path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    _write_env_file(
        env_file,
        FIRECRAWL_API_KEY="fc-test",
        NM_OCD_FIRECRAWL_PROFILE="nm-ocd-verified-6",
    )
    api_csv = _write_api_csv(tmp_path)
    session_json = tmp_path / "session.json"

    class FakeBrowserClient:
        def __init__(self, **kwargs):
            pass

        def create_session(self, **kwargs):
            return {
                "success": True,
                "id": "browser-new",
                "interactiveLiveViewUrl": "https://liveview.test/new",
            }

        def execute_node(self, session_id, code):
            return {"success": True}

    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("NM_OCD_FIRECRAWL_PROFILE", raising=False)
    monkeypatch.setattr(cli_commands, "FirecrawlBrowserClient", FakeBrowserClient)
    monkeypatch.setattr(
        cli_commands,
        "scrape_wells",
        lambda config, client, **kwargs: _protected_report(),
    )
    monkeypatch.setattr(
        cli_commands, "_session_is_verified", lambda *args, **kwargs: False
    )
    _set_cli_args(
        monkeypatch,
        "scrape-wells-supervised",
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
        "--browser-session-json",
        str(session_json),
        "--verification-timeout",
        "0",
    )

    with pytest.raises(SystemExit, match="Timed out waiting"):
        cli.main()


def test_scrape_wells_supervised_stops_after_max_session_refreshes(
    tmp_path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    _write_env_file(
        env_file,
        FIRECRAWL_API_KEY="fc-test",
        NM_OCD_FIRECRAWL_PROFILE="nm-ocd-verified-6",
    )
    api_csv = _write_api_csv(tmp_path)
    session_json = tmp_path / "session.json"
    reports = [_protected_report(), _protected_report()]

    class FakeBrowserClient:
        def __init__(self, **kwargs):
            pass

        def create_session(self, **kwargs):
            return {
                "success": True,
                "id": "browser-new",
                "interactiveLiveViewUrl": "https://liveview.test/new",
            }

        def execute_node(self, session_id, code):
            return {"success": True}

    def fake_scrape_wells(config, client, **kwargs):
        return reports.pop(0)

    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("NM_OCD_FIRECRAWL_PROFILE", raising=False)
    monkeypatch.setattr(cli_commands, "FirecrawlBrowserClient", FakeBrowserClient)
    monkeypatch.setattr(cli_commands, "scrape_wells", fake_scrape_wells)
    monkeypatch.setattr(
        cli_commands, "_session_is_verified", lambda *args, **kwargs: True
    )
    _set_cli_args(
        monkeypatch,
        "scrape-wells-supervised",
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
        "--browser-session-json",
        str(session_json),
        "--max-session-refreshes",
        "1",
    )

    with pytest.raises(SystemExit, match="after 1 supervised session refreshes"):
        cli.main()


def test_load_db_command_replaces_schema_and_loads_scraped_rows(
    tmp_path, monkeypatch
) -> None:
    api_csv = _write_api_csv(tmp_path)
    source_csv = tmp_path / "wells.csv"
    database = tmp_path / "api_well_data.db"
    with source_csv.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file, fieldnames=["API", "Operator", "Latitude", "Longitude"]
        )
        writer.writeheader()
        writer.writerow(
            {
                "API": API_NUMBER,
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

    _set_cli_args(
        monkeypatch,
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


def _write_env_file(path: Path, **values: str) -> None:
    path.write_text(
        "\n".join(f"{key}={value}" for key, value in values.items()),
        encoding="utf-8",
    )


def _write_api_csv(tmp_path: Path) -> Path:
    api_csv = tmp_path / "apis.csv"
    api_csv.write_text(f"api\n{API_NUMBER}\n", encoding="utf-8")
    return api_csv


def _set_cli_args(monkeypatch, command: str, *args: str) -> None:
    monkeypatch.setattr(sys, "argv", ["synmax", command, *args])


def _protected_report() -> dict:
    return {
        "scraped_count": 0,
        "requested_count": 1,
        "missing_count": 1,
        "missing_apis": ["3004535432"],
        "blocked_count": 1,
        "blocked_apis": ["3004535432"],
        "stopped_reason": "Stopped after 1 consecutive protected pages.",
    }


def _failed_report() -> dict:
    return {
        "scraped_count": 0,
        "requested_count": 1,
        "missing_count": 1,
        "missing_apis": ["3004535432"],
        "blocked_count": 0,
        "failed_count": 1,
        "parse_failures": {
            "3004535432": {
                "url": "https://example.test/well",
                "reason": "Browser session returned no page snapshot",
            }
        },
        "stopped_reason": "Stopped after 1 consecutive failed pages.",
    }
