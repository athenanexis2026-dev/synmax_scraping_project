# Scraping Flow

Think of the scraping flow as a chain of handoffs. Each layer has a specific job:

- `Makefile` starts the command.
- `app/cli/__main__.py` makes `python -m app.cli` executable.
- `app/cli/commands.py` parses CLI arguments, loads environment values, builds config, and builds the browser-session scraping client.
- `app/services/ingestion.py` owns the scraping loop, retries, checkpointing, and output writing.
- `app/services/well_details/clients.py` asks Firecrawl to fetch page content through a live browser session.
- `app/services/well_details/parser.py` extracts well fields from the returned content.
- `app/utils/normalize.py` cleans parsed data into the expected schema.

The short version is:

```text
Makefile
  -> CLI command
  -> command handler builds config/client
  -> scrape_wells(...)
  -> Firecrawl browser fetches page content
  -> parser extracts fields
  -> normalizer cleans fields
  -> checkpoint, CSV, and report are written
```

## 1. Makefile Starts It

The first user-facing entrypoint is:

```makefile
scraping:
	set -a; [ ! -f .env ] || . ./.env; set +a; .venv/bin/python -m app.cli scrape-wells
```

The Makefile does three things:

1. Loads environment variables from `.env`.
2. Uses the project virtual environment: `.venv/bin/python`.
3. Runs the CLI package with the command `scrape-wells`.

That means:

```text
make scraping
  -> .venv/bin/python -m app.cli scrape-wells
```

For the full ingest path:

```makefile
ingest: scraping load-db
```

`make ingest` runs scraping first. If scraping fails, `load-db` does not run.

## 2. The CLI Parses The Command

In `app/cli/commands.py`, `main()` does this:

```python
parser = build_parser()
args = parser.parse_args()
load_env_file(args.env_file)
args.func(args)
```

This is the CLI dispatcher.

Parsing command-line arguments means Python looks at the words passed after `python -m app.cli` and turns them into a structured `args` object.

For example:

```bash
python -m app.cli scrape-wells --max-retries 5 --no-resume
```

is read as:

```text
scrape-wells
--max-retries
5
--no-resume
```

`argparse` turns that into values like:

```python
args.command = "scrape-wells"
args.max_retries = 5
args.no_resume = True
args.func = scrape_wells_command
```

If the user does not pass an option, `argparse` fills in the default from `add_argument(...)`.

The command-to-function binding happens in `_add_scraping_command()`:

```python
scrape = subparsers.add_parser("scrape-wells", ...)
_add_scrape_options(scrape)
scrape.set_defaults(func=scrape_wells_command)
```

So the flow becomes:

```text
make scraping
  -> python -m app.cli scrape-wells
  -> app/cli/__main__.py
  -> commands.main()
  -> scrape_wells_command(args)
```

`args` is the bridge between the terminal command and the Python function.

## 3. Two Scrape Commands Exist

There are two related scraping commands:

```text
scrape-wells
scrape-wells-supervised
```

They both use the same lower-level scraping pipeline:

```python
scrape_wells(config, client)
```

The difference is what happens when protected pages, failed pages, or Cloudflare verification issues appear.

### Normal Command: `scrape-wells`

The normal command is run by:

```bash
make scraping
```

which calls:

```bash
.venv/bin/python -m app.cli scrape-wells
```

Its handler is:

```python
scrape_wells_command(args)
```

This command does one scrape pass:

```text
Get FIRECRAWL_API_KEY
Build ScrapeConfig
Build browser-session client
Run scrape_wells(...)
Print summary
Fail if anything is still missing, unless --allow-incomplete was passed
```

If there is no active browser session, this command exits before scraping and tells the operator to create one:

```text
No active Firecrawl browser session found. Run `make open-session`, complete verification in the live browser, then retry.
```

So `scrape-wells` expects `data/firecrawl_browser_session.json` to point at a current verified Firecrawl browser session.

### Supervised Command: `scrape-wells-supervised`

The supervised command is run by:

```bash
make scraping-supervised
```

which calls:

```bash
.venv/bin/python -m app.cli scrape-wells-supervised
```

Its handler is:

```python
scrape_wells_supervised_command(args)
```

This command wraps the same `scrape_wells(...)` pipeline in a recovery loop:

```text
Ensure an active browser session exists
Run scrape_wells(...)
If everything is complete, stop successfully
If protected/failed pages caused a recoverable stop:
  close any stale active browser session
  rotate the Firecrawl profile name
  create a new Firecrawl browser session
  print the live browser URL
  wait while the user completes Cloudflare verification
  confirm the profile can parse one Well Details page
  resume scraping from the checkpoint
```

Supervised mode uses stricter scrape settings:

```text
blocked_stop_threshold = 1
failed_stop_threshold = 1
max_retries = 1
```

That means it stops quickly when protection appears, opens a verification path, and then resumes from the checkpoint instead of spending time retrying requests that are likely still blocked.

## 4. Command Handler Builds Config And Client

The normal command's setup looks like this:

```python
api_key = _required_env("FIRECRAWL_API_KEY")
config = _scrape_config_from_args(args, resume=not args.no_resume)
client = _well_details_client_for_command(args, api_key)

report = scrape_wells(config, client)
```

That means:

1. Get the Firecrawl API key from the environment.
2. Build a `ScrapeConfig` object.
3. Build the active Firecrawl browser-session client.
4. Call the actual scraping pipeline.

The config includes paths like:

```text
data/apis_pythondev_test.csv
data/api_well_data_scraped.csv
data/scrape_report.json
data/scrape_checkpoint.json
```

It also includes retry settings, request delay, stop thresholds, and whether to resume from a checkpoint.

The client comes from:

```python
_well_details_client_for_command(args, api_key)
```

That helper checks `data/firecrawl_browser_session.json` for an active session id. If no active session exists, it exits. If a session exists, it returns:

```python
FirecrawlBrowserSessionWellDetailsClient(...)
```

That client has one job: fetch Well Details content through the existing Firecrawl browser session.

## 5. Resume Controls Whether The Checkpoint Is Read

The important line in supervised mode is:

```python
resume=True if not first_run else not args.no_resume
```

That value becomes:

```python
config.resume
```

Then `scrape_wells()` uses it here:

```python
checkpoint = (
    _read_checkpoint(config.checkpoint_json)
    if config.resume
    else _empty_checkpoint()
)
```

So:

```text
config.resume = True
  -> read data/scrape_checkpoint.json
  -> skip APIs already completed

config.resume = False
  -> ignore data/scrape_checkpoint.json
  -> start with an empty checkpoint
```

On the first supervised run, the user's `--no-resume` flag is respected:

```text
first_run = True
resume = not args.no_resume
```

After supervised recovery starts, `first_run` becomes false. From then on:

```text
resume = True
```

That is important because supervised recovery depends on the checkpoint. If the scraper completes 35 wells, hits a protected page, opens a new browser session, and resumes, the next run must read `data/scrape_checkpoint.json` so it skips those 35 completed wells.

## 6. The Actual Scraping Loop Starts

The real scrape loop is:

```python
def scrape_wells(config, client, ...):
```

This function is the core pipeline.

It starts by reading API numbers and the checkpoint:

```python
api_numbers = sorted(read_api_numbers(config.api_csv))
checkpoint = (
    _read_checkpoint(config.checkpoint_json)
    if config.resume
    else _empty_checkpoint()
)
```

`read_api_numbers(...)` reads API numbers from:

```text
data/apis_pythondev_test.csv
```

It returns a `set`. A set automatically dedupes, which means it removes duplicate API numbers.

The `sorted(...)` call makes the scrape order stable and repeatable:

```text
read_api_numbers(...) -> read and dedupe API numbers
sorted(...)           -> make the scrape order stable and repeatable
```

That stable order makes checkpoint resumes, CSV output, progress messages, and reports easier to understand.

## 7. Each API Becomes One Well Details URL

Inside the loop:

```python
for index, api_number in enumerate(api_numbers):
```

If the API is already in the checkpoint's completed records, the scraper skips it:

```python
if api_number in checkpoint["completed"]:
    continue
```

For each remaining API number, the scraper builds the official Well Details URL:

```python
url = build_well_details_url(api_number)
```

That function turns an API number into a URL like:

```text
https://wwwapps.emnrd.nm.gov/OCD/OCDPermitting/Data/WellDetails.aspx?api=30-...
```

Then the loop asks `_scrape_one_api(...)` to handle that one well.

## 8. One API Is Scraped With `_scrape_one_api()`

The call looks like this:

```python
record = _scrape_one_api(api_number, url, client, ...)
```

This function handles exactly one API number.

It receives:

```text
api_number
url
client
config
sleeper
```

Its job is:

```text
For this one API:
  fetch the page
  parse the page
  normalize the record
  retry if temporary errors happen
  return one clean row
```

The core lines are:

```python
html_text = client.scrape_html(url)
parsed_record = parse_well_details_html(html_text, expected_api=api_number)
normalized = normalize_record(parsed_record)
```

That means:

```text
client.scrape_html(url)
  -> fetch page content

parse_well_details_html(...)
  -> extract well fields from the page content

normalize_record(...)
  -> clean the fields into the expected output schema
```

`_scrape_one_api()` does not need to know how the page content was fetched. In production, it comes from a Firecrawl browser session. In tests, it can come from a fake client. The ingestion pipeline only requires a client with a `scrape_html(url)` method.

## 9. Firecrawl Fetches The Page

The production fetch happens in:

```python
FirecrawlBrowserSessionWellDetailsClient.scrape_html()
```

That client tells the active Firecrawl browser session to navigate to the official NM OCD page and return a page snapshot. It does not call Firecrawl's normal `/v2/scrape` endpoint for Well Details pages.

The command it runs inside the Firecrawl browser session is:

```bash
agent-browser open <url> && sleep ... && agent-browser snapshot
```

A snapshot is not raw HTML. It is a text representation of what the browser can see on the page, often similar to an accessibility tree. It contains visible page elements like headings, labels, links, and text.

For example, instead of raw HTML like:

```html
<span class="fw-bold">Operator:</span>
<span class="text-mute">Some Operator</span>
```

a snapshot might contain browser output like:

```text
- heading "General Well Information"
- StaticText "Operator:"
- StaticText "Some Operator"
- StaticText "Status:"
- StaticText "Active"
```

The browser-session client then converts that snapshot back into parser-friendly HTML:

```python
well_details_snapshot_to_html(snapshot)
```

That lets the project reuse the same parser path.

## 10. Parser Extracts Well Details

Once HTML comes back, parsing happens in:

```python
parse_well_details_html(html_text, expected_api=api_number)
```

The parser does not extract fields from a JSON API response. It reads them from the Well Details page markup.

In production, the flow is:

```text
Firecrawl browser session returns a browser snapshot
  -> well_details_snapshot_to_html(snapshot)
  -> parse_well_details_html(synthetic_html)
```

So `parse_well_details_html(...)` still receives HTML, but for real scraping that HTML is synthetic parser-friendly markup created from the live browser snapshot.

The NM OCD page displays most values as label/value pairs. In the raw HTML, those pairs look roughly like this:

```html
<span class="fw-bold">Operator:</span>
<span class="text-mute">[123] Example Operator</span>
```

The parser uses `_LabelValueParser` to scan the HTML for:

```text
span.fw-bold   -> field label
span.text-mute -> field value
```

Then `LABEL_TO_COLUMN` maps page labels into output column names. For example:

```text
Operator              -> Operator
Status                -> Status
Well Type             -> Well Type
Work Type             -> Work Type
Direction             -> Directional Status
Single / Multi Compl  -> Single/Multiple Completion
True Vertical Depth   -> TVD
```

This extracts fields like:

```text
Operator
Status
Well Type
Work Type
Directional Status
Surface Location
Latitude
Longitude
Spud Date
TVD
```

Some fields have extra parsing:

- `Operator` has a leading numeric code stripped, so `[123] Example Operator` becomes `Example Operator`.
- `Lat / Long` is split into `Latitude`, `Longitude`, and optional `CRS`.
- `API` is extracted from a hidden `id="API"` input when present, or from an API-looking value in the page text. If neither is found, the scraper uses the `expected_api` passed in from the input CSV.

The helper `_snapshot_label_values(...)` is only used inside the browser-session conversion path:

```text
FirecrawlBrowserSessionWellDetailsClient.scrape_html(...)
  -> agent-browser snapshot
  -> well_details_snapshot_to_html(snapshot)
  -> _snapshot_label_values(snapshot)
  -> synthetic HTML
  -> parse_well_details_html(synthetic HTML)
```

Its job is not to parse normal HTML. Its job is to read the visible text from the browser snapshot, find the "General Well Information" section, collect recognized labels such as `Operator`, `Status`, and `Lat / Long`, stop before the `History` section, and return label/value groups.

`parse_well_details_html(...)` also checks whether the page is protected by Cloudflare or returned a "do not scrape" style page. If so, it raises `ProtectedPageError`.

## 11. Normalize The Parsed Record

After parsing:

```python
normalized = normalize_record(parsed_record)
```

Parsing extracts data from the page. Normalizing makes the data match the project's expected CSV/database shape.

Normalization handles things like:

- cleaning whitespace
- converting empty values into consistent empty/null values
- keeping only expected output columns
- making the scraped record compatible with the later database load step

So the single-record flow is:

```text
URL
  -> client.scrape_html(url)
  -> raw/synthetic page HTML
  -> parse_well_details_html(...)
  -> parsed well fields
  -> normalize_record(...)
  -> clean output row
```

## 12. Results Are Written

After each API is handled, `scrape_wells()` persists output:

```python
_persist_outputs(config, api_numbers, checkpoint, stopped_reason)
```

That writes three files:

```text
data/scrape_checkpoint.json
data/api_well_data_scraped.csv
data/scrape_report.json
```

The checkpoint stores completed, blocked, and failed APIs. The CSV stores completed normalized records. The report stores a summary of what happened, including counts and any missing APIs.

If a protected page is detected, the report can include a `stopped_reason`. Supervised mode uses that report to decide whether to rotate the Firecrawl profile and open a new browser verification session.

## 13. Firecrawl's Role In The Process

Firecrawl is the remote browser layer.

Firecrawl has one role here: provide a live remote browser session that the Python scraper can drive.

```text
Active browser session exists
  -> use FirecrawlBrowserSessionWellDetailsClient
  -> navigate inside the already-open Firecrawl browser
```

`FirecrawlBrowserClient` creates a remote browser session. That session gives you an interactive URL. A human can open it and complete Cloudflare or Turnstile if needed.

Then the scraper can reuse that same session with:

```python
FirecrawlBrowserSessionWellDetailsClient
```

Firecrawl is doing the external-web work:

- loading JavaScript-rendered pages
- using a browser-like environment
- keeping a persistent profile and cookies
- giving a human a live verification window
- returning browser-visible text back to Python

Your local app is doing the data pipeline work:

- deciding which APIs to scrape
- building Well Details URLs
- requiring an active Firecrawl browser session
- parsing returned content
- normalizing records
- writing CSV, checkpoint, and report files
- stopping safely when protected pages appear

The cleanest summary is:

```text
Python controls the scrape.
Firecrawl runs the live browser session.
Parser extracts data.
Ingestion writes durable outputs.
```

Firecrawl is not the parser and not the database layer. It is the remote browser layer that gets visible page content into the Python pipeline.

## Full Flow Summary

```text
make scraping
  -> Makefile loads .env
  -> .venv/bin/python -m app.cli scrape-wells
  -> app/cli/__main__.py calls main()
  -> app/cli/commands.py parses CLI command
  -> scrape_wells_command()
  -> builds ScrapeConfig
  -> requires active Firecrawl browser session
  -> builds FirecrawlBrowserSessionWellDetailsClient
  -> app/services/ingestion.py scrape_wells()
  -> reads API CSV
  -> reads or creates checkpoint
  -> loops over API numbers
  -> skips completed APIs from checkpoint
  -> builds WellDetails.aspx URL
  -> _scrape_one_api()
  -> client.scrape_html(url)
  -> Firecrawl browser session opens page and returns snapshot
  -> snapshot is converted into parser-friendly HTML
  -> parser extracts fields
  -> normalize_record()
  -> write CSV, checkpoint, and report
```

For supervised scraping, the same flow is wrapped in recovery:

```text
make scraping-supervised
  -> scrape_wells_supervised_command()
  -> ensure a verified browser session exists
  -> run scrape_wells(...)
  -> if protected/failed pages stop the scrape:
       close stale session
       rotate Firecrawl profile
       create a new session
       wait for manual verification
       resume from data/scrape_checkpoint.json
```
