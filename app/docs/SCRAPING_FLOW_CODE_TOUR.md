# Scraping Flow Code Tour

The goal is not to explain every line. The goal is to show that you understand the path from a terminal command, through the CLI, into Firecrawl, then into parsing, normalization, checkpointing, and output files.

## Quick Interview Summary

Say this first:

```text
The scraper starts from a Makefile command, dispatches into the Python CLI, builds a ScrapeConfig and a Firecrawl browser-session client, then the ingestion service loops through API numbers. For each API, it builds the official NM OCD Well Details URL, opens it through the active Firecrawl browser session, converts the browser snapshot into parser-friendly HTML, parses well fields, normalizes them to the database schema, and writes the CSV, checkpoint, and report after each API.
```

Then walk through the functions in this order.

## 1. Start At The Makefile

Visit:

```text
Makefile
```

Point to:

```makefile
scraping:
	set -a; [ ! -f .env ] || . ./.env; set +a; .venv/bin/python -m app.cli scrape-wells

scraping-supervised:
	set -a; [ ! -f .env ] || . ./.env; set +a; .venv/bin/python -m app.cli scrape-wells-supervised

ingest: scraping load-db
ingest-supervised: scraping-supervised load-db
```

Explain:

- `make scraping` runs the normal scrape command.
- `make scraping-supervised` runs the recovery-friendly scrape command.
- `make ingest` means scrape first, then load the scraped CSV into SQLite.
- The important handoff is `.venv/bin/python -m app.cli scrape-wells`.

Next visit:

```text
app/cli/__main__.py
```

## 2. Show How `python -m app.cli` Enters The CLI

Visit:

```text
app/cli/__main__.py
```

Point to:

```python
from app.cli import main

if __name__ == "__main__":
    main()
```

Explain:

- This file makes `python -m app.cli` executable.
- It immediately hands control to `main()` in `app/cli/commands.py`.

Next visit:

```text
app/cli/commands.py -> main()
```

## 3. Show The CLI Dispatcher

Visit:

```text
app/cli/commands.py -> main()
```

Point to:

```python
parser = build_parser()
args = parser.parse_args()
load_env_file(args.env_file)
args.func(args)
```

Explain:

- `build_parser()` defines all CLI commands.
- `parse_args()` turns terminal words into an `args` object.
- `load_env_file()` loads `.env` values like `FIRECRAWL_API_KEY`.
- `args.func(args)` dispatches to the handler for the selected command.

Next visit:

```text
app/cli/commands.py -> build_parser()
app/cli/commands.py -> _add_scraping_command()
```

## 4. Show How The Scrape Commands Are Registered

Visit:

```text
app/cli/commands.py -> build_parser()
app/cli/commands.py -> _add_scraping_command()
```

Point to:

```python
scrape.set_defaults(func=scrape_wells_command)
supervised.set_defaults(func=scrape_wells_supervised_command)
```

Explain:

- `scrape-wells` is connected to `scrape_wells_command`.
- `scrape-wells-supervised` is connected to `scrape_wells_supervised_command`.
- Both commands eventually call the same lower-level ingestion pipeline: `scrape_wells(config, client)`.
- The difference is session recovery: supervised mode can create or refresh a Firecrawl browser session and wait for manual verification.

Next visit:

```text
app/cli/commands.py -> scrape_wells_command()
```

## 5. Explain The Normal Scrape Command

Visit:

```text
app/cli/commands.py -> scrape_wells_command()
```

Point to:

```python
api_key = _required_env("FIRECRAWL_API_KEY")
config = _scrape_config_from_args(...)
client = _well_details_client_for_command(args, api_key)

report = scrape_wells(config, client, ...)
```

Explain:

- This function is setup, not the scrape loop itself.
- It reads the required Firecrawl API key.
- It builds a `ScrapeConfig`.
- It builds the Firecrawl browser-session client.
- Then it calls `scrape_wells(config, client)`.

Important phrase:

```text
The CLI prepares configuration and dependencies. The actual scraping loop lives in app/services/ingestion.py.
```

Next visit:

```text
app/cli/commands.py -> _scrape_config_from_args()
```

## 6. Show The Scrape Configuration

Visit:

```text
app/cli/commands.py -> _scrape_config_from_args()
```

Explain:

- This function collects all scrape settings into one `ScrapeConfig`.
- The important paths are:

```text
data/apis_pythondev_test.csv
data/api_well_data_scraped.csv
data/scrape_report.json
data/scrape_checkpoint.json
```

- It also controls retry count, request delay, checkpoint resume, protected-page stop threshold, and failed-page stop threshold.

Next visit:

```text
app/cli/commands.py -> _well_details_client_for_command()
```

## 7. Show The One Firecrawl Strategy

Visit:

```text
app/cli/commands.py -> _well_details_client_for_command()
```

Point to:

```python
session_id = _active_browser_session_id(args.browser_session_json)
if not session_id:
    raise SystemExit(...)

return FirecrawlBrowserSessionWellDetailsClient(...)
```

Explain:

- This project now has one production scraping strategy: use an active Firecrawl browser session.
- The session ID comes from `data/firecrawl_browser_session.json`.
- If there is no active session, normal scraping exits before it starts.


Important phrase:

```text
The scraper is intentionally browser-session-first because the NM OCD site can show Cloudflare or Turnstile protection. A human may need to verify the live Firecrawl browser before scraping continues.
```

Next visit:

```text
app/services/ingestion.py -> scrape_wells()
```

## 8. Show The Main Ingestion Loop

Visit:

```text
app/services/ingestion.py -> scrape_wells()
```

Point to:

```python
api_numbers = sorted(read_api_numbers(config.api_csv))
checkpoint = _read_checkpoint(...) if config.resume else _empty_checkpoint()

for index, api_number in enumerate(api_numbers):
    if api_number in checkpoint["completed"]:
        continue

    url = build_well_details_url(api_number)
    record = _scrape_one_api(...)
```

Explain:

- `read_api_numbers()` reads and deduplicates the input CSV.
- `sorted(...)` makes the scrape order deterministic.
- The checkpoint lets the scraper resume instead of starting over.
- Completed APIs are skipped.
- Each API gets converted into the official NM OCD Well Details URL.
- `_scrape_one_api()` handles fetch, parse, normalize, and retry for one well.

Heartbeat/pacing note:

```text
The heartbeat/sleep is not my main anti-bot strategy. The main strategy is using a verified browser session. The delay is just polite pacing and a configurable safety valve. The heartbeat version makes longer waits easier to test and easier to adjust, but I would not claim it is what prevents security challenges.
```

Next visit:

```text
app/utils/normalize.py -> read_api_numbers()
app/services/well_details/urls.py -> build_well_details_url()
```

## 9. Show Input Reading And URL Building

Visit:

```text
app/utils/normalize.py -> read_api_numbers()
```

Explain:

- Reads API numbers from a CSV.
- Supports a header with an API column or one API per row.
- Normalizes API numbers to digits.
- Returns a `set`, which removes duplicates.

Checkpoint/resume note:

```text
If resume mode is on, the scraper loads previous scrape progress from data/scrape_checkpoint.json. If resume mode is off, it creates a new empty checkpoint and scrapes everything again. This is what makes the scraper resumable: if the scrape stops halfway through, the next run can read the checkpoint and skip API numbers that were already completed.
```

Then visit:

```text
app/services/well_details/urls.py -> build_well_details_url()
```

Explain:

- Converts a digit-only API into the NM OCD hyphenated format.
- Builds a URL like:

```text
https://wwwapps.emnrd.nm.gov/OCD/OCDPermitting/Data/WellDetails.aspx?api=30-015-25325
```

Next visit:

```text
app/services/ingestion.py -> _scrape_one_api()
```

## 10. Show One API Being Scraped

Visit:

```text
app/services/ingestion.py -> _scrape_one_api()
```

Point to:

```python
html_text = client.scrape_html(url)
parsed_record = parse_well_details_html(html_text, expected_api=api_number)
normalized = normalize_record(parsed_record)
```

Explain:

- This is the core per-well unit of work.
- `client.scrape_html(url)` fetches page content.
- `parse_well_details_html(...)` extracts fields from the page.
- `normalize_record(...)` maps those fields into the final schema.
- It retries temporary browser, parse, Firecrawl, and value errors.
- It does not retry `ProtectedPageError` because immediate retry usually will not solve Cloudflare or Turnstile protection.

Next visit:

```text
app/services/well_details/clients.py -> FirecrawlBrowserSessionWellDetailsClient.scrape_html()
```

## 11. Show Firecrawl Fetching Through The Browser Session

Visit:

```text
app/services/well_details/clients.py -> FirecrawlBrowserSessionWellDetailsClient.scrape_html()
```

Point to:

```python
response = self.browser_client.execute_bash(
    self.session_id,
    (
        f"agent-browser open {shlex.quote(url)} && "
        f"sleep {max(0, self.wait_for_ms / 1000):g} && "
        "agent-browser snapshot"
    ),
)
snapshot = text_from_browser_execute_response(response)
return well_details_snapshot_to_html(snapshot)
```

Explain:

- This is where Firecrawl actually touches the external website.
- It opens the Well Details URL inside the active Firecrawl browser session.
- It waits briefly for the page to load.
- It asks Firecrawl for a browser snapshot.
- The snapshot is converted into parser-friendly HTML.

Next visit:

```text
app/services/well_details/parser.py -> well_details_snapshot_to_html()
```

## 12. Show Snapshot Conversion

Visit:

```text
app/services/well_details/parser.py -> well_details_snapshot_to_html()
app/services/well_details/parser.py -> _snapshot_label_values()
```

Explain:

- A browser snapshot is visible text/accessibility-style output, not raw HTML.
- `well_details_snapshot_to_html()` first checks whether the snapshot is protected content.
- `_snapshot_label_values()` finds the "General Well Information" section.
- It collects labels like `Operator`, `Status`, `Well Type`, `Lat / Long`, and `True Vertical Depth`.
- Then it creates simple HTML that looks like the NM OCD label/value structure.

Important phrase:

```text
The parser still consumes HTML, but in production that HTML is synthetic markup created from the browser snapshot.
```

Next visit:

```text
app/services/well_details/parser.py -> parse_well_details_html()
```

## 13. Show Field Parsing

Visit:

```text
app/services/well_details/parser.py -> parse_well_details_html()
```

Explain:

- `_LabelValueParser` extracts label/value pairs from the HTML.
- `LABEL_TO_COLUMN` maps page labels into output columns.
- It cleans the operator name by stripping leading numeric codes.
- It splits `Lat / Long` into `Latitude`, `Longitude`, and optional `CRS`.
- It uses the expected API from the input CSV if the page does not expose one clearly.

Next visit:

```text
app/utils/normalize.py -> normalize_record()
```

## 14. Show Normalization

Visit:

```text
app/utils/normalize.py -> normalize_record()
```

Explain:

- The parser extracts source values from the page.
- `normalize_record()` converts those values into the exact `api_well_data` table columns.
- It fills every assignment column, coerces values, repairs known Well Details field shapes, normalizes the API number, and builds a surface location when needed.

Important phrase:

```text
Parsing understands the webpage. Normalization understands our database schema.
```

Next visit:

```text
app/services/ingestion.py -> scrape_wells()
app/services/ingestion.py -> _persist_outputs()
```

## 15. Return To The Loop And Show Persistence

Visit:

```text
app/services/ingestion.py -> scrape_wells()
```

Point to the success and error branches:

```python
checkpoint["completed"][api_number] = record
checkpoint["blocked"][api_number] = ...
checkpoint["failures"][api_number] = ...
```

Explain:

- Successful APIs go into `checkpoint["completed"]`.
- Protected pages go into `checkpoint["blocked"]`.
- Browser, parse, and value failures go into `checkpoint["failures"]`.
- Consecutive blocked or failed pages can stop the run so the session can be refreshed.

Then visit:

```text
app/services/ingestion.py -> _persist_outputs()
```

Explain:

- The scraper writes durable output after each API.
- It writes:

```text
data/scrape_checkpoint.json
data/api_well_data_scraped.csv
data/scrape_report.json
```

- This makes the process resumable and gives the operator a report even if the run stops early.

## 16. If They Ask About Supervised Recovery

Visit:

```text
app/cli/commands.py -> scrape_wells_supervised_command()
```

Explain:

- Supervised mode wraps the same `scrape_wells(config, client)` pipeline in a recovery loop.
- It starts by calling `_ensure_active_browser_session(...)`.
- It uses stricter settings: stop quickly after protected or failed pages.
- If recovery is possible, it closes the stale browser session, rotates the Firecrawl profile, opens a new session, waits for manual verification, and resumes from the checkpoint.

Then visit:

```text
app/cli/commands.py -> _ensure_active_browser_session()
app/cli/commands.py -> _create_browser_session_for_api()
app/cli/commands.py -> _wait_for_profile_verification()
app/cli/commands.py -> _session_is_verified()
```

Explain:

- `_ensure_active_browser_session()` makes sure there is a session before supervised scraping starts.
- `_create_browser_session_for_api()` calls Firecrawl `/browser`, saves session metadata, and opens a Well Details URL.
- `_wait_for_profile_verification()` waits while the human completes Cloudflare or Turnstile in the live browser.
- `_session_is_verified()` tests the session by scraping and parsing one Well Details page.

Important phrase:

```text
Supervised mode does not use a different scraper. It uses the same scraper, but it adds browser-session recovery around it.
```

## Final Interview Walkthrough Order

Use this order if you only have a few minutes:

```text
1. Makefile -> scraping / scraping-supervised / ingest
2. app/cli/__main__.py -> main()
3. app/cli/commands.py -> main()
4. app/cli/commands.py -> _add_scraping_command()
5. app/cli/commands.py -> scrape_wells_command()
6. app/cli/commands.py -> _scrape_config_from_args()
7. app/cli/commands.py -> _well_details_client_for_command()
8. app/services/ingestion.py -> scrape_wells()
9. app/utils/normalize.py -> read_api_numbers()
10. app/services/well_details/urls.py -> build_well_details_url()
11. app/services/ingestion.py -> _scrape_one_api()
12. app/services/well_details/clients.py -> FirecrawlBrowserSessionWellDetailsClient.scrape_html()
13. app/services/well_details/parser.py -> well_details_snapshot_to_html()
14. app/services/well_details/parser.py -> parse_well_details_html()
15. app/utils/normalize.py -> normalize_record()
16. app/services/ingestion.py -> _persist_outputs()
```

## One-Sentence Close

End with:

```text
The key design is separation of concerns: the CLI handles commands and configuration, Firecrawl handles the remote browser session, ingestion handles retry/checkpoint/output behavior, the parser understands the Well Details page, and normalization turns parsed values into the database shape.
```
