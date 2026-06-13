import csv
import json

from app.services.ingestion import ScrapeConfig, scrape_wells
from app.services.well_details.errors import FirecrawlBrowserError


def _well_html(api: str) -> str:
    return f"""
    <input type="hidden" id="API" value="{api}"/>
    <div id="datapane">
      <span class="fw-bold">Operator:</span>
      <span class="text-mute">[123] Example Operator</span>
      <span class="fw-bold">Status:</span>
      <span class="text-mute">Active</span>
      <span class="fw-bold">Well Type:</span>
      <span class="text-mute">Oil</span>
      <span class="fw-bold">Lat / Long:</span>
      <span class="text-mute">32.50,-104.25 NAD83</span>
    </div>
    """


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def scrape_html(self, url: str) -> str:
        self.urls.append(url)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def test_scrape_wells_writes_csv_report_and_checkpoint(tmp_path) -> None:
    api_csv = tmp_path / "apis.csv"
    api_csv.write_text("api\n30-045-35432\n30-045-35433\n", encoding="utf-8")
    config = ScrapeConfig(
        api_csv=api_csv,
        output_csv=tmp_path / "wells.csv",
        report_json=tmp_path / "report.json",
        checkpoint_json=tmp_path / "checkpoint.json",
        request_delay_seconds=0,
        max_retries=1,
        retry_backoff_seconds=0,
    )
    client = FakeClient([_well_html("30-045-35432"), _well_html("30-045-35433")])

    report = scrape_wells(config, client, sleeper=lambda _: None)

    assert report["scraped_count"] == 2
    assert report["missing_count"] == 0
    assert len(client.urls) == 2

    with config.output_csv.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))
    assert [row["API"] for row in rows] == ["3004535432", "3004535433"]
    assert rows[0]["Operator"] == "Example Operator"

    saved_report = json.loads(config.report_json.read_text(encoding="utf-8"))
    checkpoint = json.loads(config.checkpoint_json.read_text(encoding="utf-8"))
    assert saved_report["source"] == "WellDetails.aspx"
    assert sorted(checkpoint["completed"]) == ["3004535432", "3004535433"]

    resume_client = FakeClient([])
    resumed_report = scrape_wells(config, resume_client, sleeper=lambda _: None)

    assert resumed_report["scraped_count"] == 2
    assert resume_client.urls == []


def test_scrape_wells_stops_after_repeated_protected_pages(tmp_path) -> None:
    api_csv = tmp_path / "apis.csv"
    api_csv.write_text("api\n30-045-35432\n30-045-35433\n30-045-35434\n", encoding="utf-8")
    config = ScrapeConfig(
        api_csv=api_csv,
        output_csv=tmp_path / "wells.csv",
        report_json=tmp_path / "report.json",
        checkpoint_json=tmp_path / "checkpoint.json",
        request_delay_seconds=0,
        blocked_stop_threshold=2,
    )
    protected_html = (
        "<html><script src='https://challenges.cloudflare.com/turnstile/v0/api.js'>"
        "</script><body>Just a moment</body></html>"
    )
    client = FakeClient([protected_html, protected_html, _well_html("30-045-35434")])

    report = scrape_wells(config, client, sleeper=lambda _: None)

    assert report["scraped_count"] == 0
    assert report["blocked_count"] == 2
    assert report["missing_count"] == 3
    assert report["stopped_reason"].startswith("Stopped after 2")
    assert len(client.urls) == 2


def test_scrape_wells_records_browser_session_failures(tmp_path) -> None:
    api_csv = tmp_path / "apis.csv"
    api_csv.write_text("api\n30-045-35432\n", encoding="utf-8")
    config = ScrapeConfig(
        api_csv=api_csv,
        output_csv=tmp_path / "wells.csv",
        report_json=tmp_path / "report.json",
        checkpoint_json=tmp_path / "checkpoint.json",
        request_delay_seconds=0,
        max_retries=1,
        retry_backoff_seconds=0,
    )
    client = FakeClient([FirecrawlBrowserError("Browser session returned no page snapshot")])

    report = scrape_wells(config, client, sleeper=lambda _: None)

    assert report["scraped_count"] == 0
    assert report["failed_count"] == 1
    assert report["parse_failures"]["3004535432"]["reason"].startswith(
        "Failed after 1 attempts"
    )


def test_scrape_wells_can_stop_after_first_failed_page(tmp_path) -> None:
    api_csv = tmp_path / "apis.csv"
    api_csv.write_text("api\n30-045-35432\n30-045-35433\n", encoding="utf-8")
    config = ScrapeConfig(
        api_csv=api_csv,
        output_csv=tmp_path / "wells.csv",
        report_json=tmp_path / "report.json",
        checkpoint_json=tmp_path / "checkpoint.json",
        request_delay_seconds=0,
        max_retries=1,
        retry_backoff_seconds=0,
        failed_stop_threshold=1,
    )
    client = FakeClient(
        [
            FirecrawlBrowserError("Browser session returned no page snapshot"),
            _well_html("30-045-35433"),
        ]
    )

    report = scrape_wells(config, client, sleeper=lambda _: None)

    assert report["scraped_count"] == 0
    assert report["failed_count"] == 1
    assert report["missing_count"] == 2
    assert report["stopped_reason"].startswith("Stopped after 1 consecutive failed pages")
    assert len(client.urls) == 1
