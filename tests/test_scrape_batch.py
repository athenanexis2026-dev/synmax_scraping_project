import json

from app.scrape_batch import parse_cached_html, scrape_api_file, summarize_results


VERIFIED_HTML = """
<div id="datapane" data-uc="GetWellHeader">
  <div>
    <span class="fw-bold nowrap w-150px">Operator:</span>
    <span class="text-mute ms-1">[371838] DJR OPERATING, LLC</span>
  </div>
  <div class="d-flex">
    <span class="fw-bold nowrap w-150px">Status:</span>
    <span class="text-mute ms-2">Active</span>
  </div>
  <div class="d-flex">
    <span class="fw-bold nowrap w-150px">Lat / Long:</span>
    <span class="text-mute ms-2">36.3313293,-107.8383865 NAD83</span>
  </div>
</div>
"""


def test_parse_cached_html_returns_cached_result(tmp_path) -> None:
    cache_path = tmp_path / "3004535432.html"
    cache_path.write_text(VERIFIED_HTML, encoding="utf-8")

    result = parse_cached_html("3004535432", cache_path)

    assert result.status == "cached"
    assert result.record["Operator"] == "DJR OPERATING, LLC"
    assert result.record["Latitude"] == 36.3313293


def test_scrape_api_file_uses_existing_cache_and_writes_report(tmp_path) -> None:
    api_csv = tmp_path / "apis.csv"
    api_csv.write_text("api\n30-045-35432\n", encoding="utf-8")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "3004535432.html").write_text(VERIFIED_HTML, encoding="utf-8")
    report_path = tmp_path / "reports" / "scrape.jsonl"

    results = scrape_api_file(api_csv, cache_dir, report_path, delay_seconds=0)

    assert summarize_results(results) == {"scraped": 0, "cached": 1, "gated": 0, "error": 0}
    report_lines = report_path.read_text(encoding="utf-8").splitlines()
    assert len(report_lines) == 1
    assert json.loads(report_lines[0])["status"] == "cached"


def test_parse_cached_html_reports_gated_page(tmp_path) -> None:
    cache_path = tmp_path / "3004535432.html"
    cache_path.write_text('<div class="cf-turnstile">Verifying you’re human…</div>', encoding="utf-8")

    result = parse_cached_html("3004535432", cache_path)

    assert result.status == "gated"
    assert "Turnstile" in result.error
