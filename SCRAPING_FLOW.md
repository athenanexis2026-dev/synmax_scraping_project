# Scraping Flow

Think of the scraping flow as a chain of handoffs. Each layer has a specific job:

- `Makefile` starts the command.
- `app/cli/__main__.py` makes `python -m app.cli` executable.
- `app/cli/commands.py` parses CLI arguments, loads environment values, and chooses the scraping client.
- `app/services/ingestion.py` owns the scraping loop, retries, checkpointing, and output writing.
- `app/services/well_details/clients.py` asks Firecrawl to fetch page content.
- `app/services/well_details/parser.py` extracts well fields from the returned content.
- `app/utils/normalize.py` cleans parsed data into the expected schema.

## 1. Makefile Starts It

The first user-facing entrypoint is:

```makefile
scraping:
	set -a; [ ! -f .env ] || . ./.env; set +a; .venv/bin/python -m app.cli scrape-wells
```

When you run:

```bash
make scraping
```

the Makefile does three things:

1. Loads environment variables from `.env`.
2. Uses the project virtual environment: `.venv/bin/python`.
3. Runs the CLI package with the command `scrape-wells`.

The important part is:

```bash
python -m app.cli scrape-wells
```

That means: run the Python package `app.cli`, and pass it the command `scrape-wells`.

## 5. CLI Parses The Command

In `commands.py`, `main()` does this:

```python
parser = build_parser()
args = parser.parse_args()
load_env_file(args.env_file)
args.func(args)
```

This is the CLI dispatcher.

It:

1. Builds all available CLI commands.
2. Parses the command-line arguments.
3. Loads `.env`.
4. Calls the function attached to the selected command.

Since the Makefile passed:

```bash
scrape-wells
```

the selected function becomes:

```python
scrape_wells_command
```

That binding happens in `_add_scraping_command()`:

```python
scrape = subparsers.add_parser("scrape-wells", ...)
_add_scrape_options(scrape)
scrape.set_defaults(func=scrape_wells_command)
```

So the flow is:

```text
make scraping
  -> python -m app.cli scrape-wells
  -> app/cli/__main__.py
  -> commands.main()
  -> scrape_wells_command(args)
```

## 6. Two Scrape Commands Exist

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
Build config
Choose client
Run scrape_wells(...)
Print summary
Fail if anything is still missing, unless --allow-incomplete was passed
```

If Cloudflare blocks pages and the scrape is incomplete, this command does not automatically create a new browser session. It exits with guidance like:

```text
Run `make open-session`, verify the page, then `make close-session` and retry.
```

So `scrape-wells` is the simpler path. It expects the current browser session or saved Firecrawl profile to already be good enough.

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

Supervised mode also uses stricter scrape settings:

```text
blocked_stop_threshold = 1
failed_stop_threshold = 1
max_retries = 1
```

That means it stops quickly when protection appears, opens a verification path, and then resumes from the checkpoint instead of spending time retrying requests that are likely still blocked.

The practical difference is:

```text
scrape-wells:
  Try the scrape once with the available client.
  If blocked/incomplete, tell the user what to do next.

scrape-wells-supervised:
  Try the scrape.
  If blocked/incomplete in a recoverable way, create a browser session,
  wait for manual Cloudflare verification, then resume automatically.
```

## 7. `scrape_wells_command()` Prepares The Scrape

The scrape command's job is setup, not the scraping loop itself.

It does these important things:

```python
api_key = _required_env("FIRECRAWL_API_KEY")
config = _scrape_config_from_args(args, resume=not args.no_resume)
client = _well_details_client_for_command(args, api_key)

report = scrape_wells(config, client)
```

That means:

1. Get the Firecrawl API key from the environment.
2. Build a `ScrapeConfig` object.
3. Choose which scraping client to use.
4. Call the actual scraping pipeline.

The config includes paths like:

```text
data/apis_pythondev_test.csv
data/api_well_data_scraped.csv
data/scrape_report.json
data/scrape_checkpoint.json
```

It also includes retry settings, request delay, and whether to resume from a checkpoint.

## 8. The Client Is Selected

The CLI chooses the client in:

```python
def _well_details_client_for_command(args, api_key):
```

The logic is:

```python
if not args.no_browser_session:
    session_id = _active_browser_session_id(args.browser_session_json)
    if session_id:
        return FirecrawlBrowserSessionWellDetailsClient(...)

return FirecrawlWellDetailsClient(...)
```

This does not mean: Cloudflare failed, so fallback to the direct endpoint.

It means: before scraping starts, choose the best available fetch strategy.

There are two possible strategies.

### Strategy 1: Use An Existing Live Browser Session

This happens only if this file exists and contains an active session:

```text
data/firecrawl_browser_session.json
```

That file is created by:

```bash
make open-session
```

or by supervised scraping.

If that session exists, the scraper uses:

```python
FirecrawlBrowserSessionWellDetailsClient
```

That is the stronger option for protected pages because a human may have already completed Cloudflare in that live Firecrawl browser.

### Strategy 2: Use Firecrawl's Normal Scrape Endpoint

If there is no active browser session, the scraper uses:

```python
FirecrawlWellDetailsClient
```

That calls Firecrawl's normal `/v2/scrape` endpoint.

This fallback exists because not every run needs a live browser session. If the Firecrawl profile or cookies are already trusted, or if the page is not currently challenging, `/v2/scrape` is simpler operationally.

It can still use a saved Firecrawl profile:

```python
profile_name=os.environ.get("NM_OCD_FIRECRAWL_PROFILE") or None
```

So `/v2/scrape` is not necessarily unverified. It can use a saved Firecrawl profile that may already contain cookies or session trust.

The normal path is:

```text
Try to scrape with active browser session if one exists.
Otherwise, use Firecrawl scrape endpoint with saved profile.
```

This distinction matters for `make ingest` and `make ingest-supervised`.

`make ingest` runs:

```text
make ingest
  -> make scraping
  -> scrape-wells
  -> choose one client before scraping starts
  -> run scrape_wells(...)
```

If no active browser session exists, `make ingest` uses `/v2/scrape` first. If `/v2/scrape` returns protected or unusable pages, `make ingest` does not create a live browser session inside that same run. It records the blocked/missing APIs, stops if the incomplete scrape is not allowed, and tells the operator to open and verify a session before retrying.

`make ingest-supervised` runs:

```text
make ingest-supervised
  -> make scraping-supervised
  -> scrape-wells-supervised
  -> choose the currently available client
  -> run scrape_wells(...)
  -> if protected/failed pages cause a recoverable stop:
       close stale browser session
       rotate Firecrawl profile
       create a new live browser session
       wait for manual verification
       resume from checkpoint
```

So supervised mode also starts by using the currently available client. The difference is what happens after protection appears: supervised mode creates and verifies a live browser session automatically, while normal ingest only reports the problem and exits.

If Cloudflare blocks the `/v2/scrape` result, the parser detects that and raises `ProtectedPageError`. Then the outer pipeline records the API as blocked and may stop after several protected pages.

That is why the workflow says to open and verify a Firecrawl browser session when protection appears.

That means Strategy 2 is not a Cloudflare bypass. It is a convenience fallback for cases where the saved profile is already trusted enough or the site is not challenging. For consistently protected pages, you probably need an active browser session path, or the CLI should fail fast and tell the user to run open-session / supervised mode instead of trying normal /v2/scrape.


## 9. The Actual Scraping Loop Starts

The real scrape loop is:

```python
def scrape_wells(config, client, ...):
```

This function is the core pipeline.

It does:

```python
api_numbers = sorted(read_api_numbers(config.api_csv))
checkpoint = _read_checkpoint(config.checkpoint_json)
```

So first it reads the API numbers from:

```text
data/apis_pythondev_test.csv
```

Then it checks the checkpoint file so it can skip wells that were already completed.

The checkpoint is what allows the scraper to resume instead of starting over every time.

## 10. For Each API Number, Build A URL

Inside the loop:

```python
for index, api_number in enumerate(api_numbers):
```

For each API number, it builds the official Well Details URL:

```python
url = build_well_details_url(api_number)
```

That function turns an API number into a URL like:

```text
https://wwwapps.emnrd.nm.gov/OCD/OCDPermitting/Data/WellDetails.aspx?api=30-...
```

## 11. One API Is Scraped With `_scrape_one_api()`

Then the loop calls:

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

That means `_scrape_one_api()` does not know whether the page came from:

- Firecrawl `/v2/scrape`
- a Firecrawl browser session
- a fake test client

It only knows: I have a client with a `scrape_html(url)` method.

That keeps the pipeline clean. The scraping pipeline does not care how the HTML is fetched.

## 12. Max Retries

The retry logic is inside `_scrape_one_api()`.

The loop looks like:

```python
for attempt in range(1, config.max_retries + 1):
    try:
        html_text = client.scrape_html(url)
        parsed_record = parse_well_details_html(html_text, expected_api=api_number)
        normalized = normalize_record(parsed_record)
        return normalized
    except ProtectedPageError:
        raise
    except (...other errors...) as error:
        last_error = error
        if attempt < config.max_retries:
            sleeper(config.retry_backoff_seconds * attempt)
```

The default max retries is:

```python
DEFAULT_MAX_RETRIES = 3
```

So for one API number, the scraper may try up to three times.

It retries errors like:

- Firecrawl request failed
- browser session failed
- parser failed
- bad or invalid values

It does not retry `ProtectedPageError` inside `_scrape_one_api()`. Protection is treated differently because Cloudflare or Turnstile usually will not be fixed by immediately trying the same request again.

If max retries is reached, this line runs:

```python
raise FirecrawlScrapeError(
    f"Failed after {config.max_retries} attempts: {last_error}"
)
```

Then the outer `scrape_wells()` function catches that failure and records it in the checkpoint:

```python
checkpoint["failures"][api_number] = {"url": url, "reason": str(error)}
```

After that, the scraper writes the current state to:

```text
data/scrape_checkpoint.json
data/api_well_data_scraped.csv
data/scrape_report.json
```

Then it may continue to the next API, unless a configured failure threshold says to stop.

So max retries does not automatically kill the whole scrape. It means: this one API failed after enough attempts; record it as failed.

## 13. Firecrawl Fetches The Page

If using the normal client, the fetch happens in:

```python
FirecrawlWellDetailsClient.scrape_html()
```

This builds a POST request to Firecrawl:

```python
payload = {
    "url": url,
    "formats": ["html", "rawHtml"],
    "onlyMainContent": False,
    ...
}
```

Then it sends that to:

```text
https://api.firecrawl.dev/v2/scrape
```

Firecrawl loads the official NM OCD page and returns HTML.

If using the browser-session client, it instead navigates an active browser session and gets a page snapshot.

## 14. What Is A Snapshot?

When using the browser-session client, the code runs this command inside the Firecrawl browser session:

```bash
agent-browser open <url> && sleep ... && agent-browser snapshot
```

A snapshot is not raw HTML.

It is a text representation of what the browser can see on the page, often similar to an accessibility tree. It contains visible page elements like headings, labels, links, and text.

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

So the flow for browser session is:

```text
Open page in live Firecrawl browser
Wait a few seconds
Take accessibility/visible-text snapshot
Extract labels and values from the snapshot
Convert those labels/values into simple HTML
Pass that HTML into the normal parser
```

That lets the project reuse the same parser path as much as possible.

## 15. Parser Extracts Well Details

Once HTML comes back, parsing happens in:

```python
parse_well_details_html(html_text, expected_api=None)
```

The parser does not extract fields from a JSON API response. It reads them from the Well Details page markup.

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

So the source of most fields is the visible "General Well Information" style content on the Well Details page itself.

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

If the page came from a live browser session, the client first converts the browser snapshot into simple parser-friendly HTML with the same label/value shape. That is why the same `parse_well_details_html()` function can handle both normal Firecrawl HTML and live-browser snapshot results.

It also checks whether the page is protected by Cloudflare or returned a "do not scrape" style page. If so, it raises `ProtectedPageError`.

## 16. Results Are Written

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

The CSV is the main scraped output.

The checkpoint tracks completed, blocked, and failed APIs.

The report summarizes scrape status: how many requested, scraped, missing, blocked, failed, and so on.

## 17. Firecrawl's Role In The Process

Firecrawl is the remote scraping and browser layer.

The Python app does not directly visit the NM OCD website with `requests`, Selenium, or local Chrome. Instead, the app asks Firecrawl to do that work.

Firecrawl has two roles here, matching the two fetch strategies chosen in `commands.py`.

### Role 1: Normal Scrape Endpoint

This role is used by Strategy 2 from the client-selection step:

```text
No active browser session exists
  -> use FirecrawlWellDetailsClient
  -> call Firecrawl /v2/scrape
```

In code, this is the fallback client:

```python
FirecrawlWellDetailsClient(
    api_key=api_key,
    profile_name=os.environ.get("NM_OCD_FIRECRAWL_PROFILE") or None,
    endpoint=_firecrawl_endpoint(),
    proxy=os.environ.get("NM_OCD_FIRECRAWL_PROXY", "auto"),
)
```

`FirecrawlWellDetailsClient` sends a POST request to:

```text
https://api.firecrawl.dev/v2/scrape
```

with a payload like:

```python
{
    "url": official_well_details_url,
    "formats": ["html", "rawHtml"],
    "onlyMainContent": False,
    "headers": {...},
    "profile": {"name": profile_name, "saveChanges": True}
}
```

Firecrawl loads the official page and returns HTML. The app then sends that HTML to:

```python
parse_well_details_html(html_text, expected_api=api_number)
```

This role is simpler, but it depends on `/v2/scrape` being able to reach real Well Details HTML. If Cloudflare returns a challenge page instead, the parser raises `ProtectedPageError`.

### Role 2: Live Browser Session

This role is used by Strategy 1 from the client-selection step:

```text
Active browser session exists
  -> use FirecrawlBrowserSessionWellDetailsClient
  -> navigate inside the already-open Firecrawl browser
```

`FirecrawlBrowserClient` can create a remote browser session:

```text
POST /v2/browser
```

That session gives you an interactive URL. A human can open it and complete Cloudflare or Turnstile if needed.

Then the scraper can reuse that same session with:

```python
FirecrawlBrowserSessionWellDetailsClient
```

That client does not call `/v2/scrape` for each page. Instead, it tells the live browser session:

```text
open this Well Details URL
wait
give me a snapshot of what is visible
```

In code, that client runs a browser command like:

```bash
agent-browser open <url> && sleep ... && agent-browser snapshot
```

Then the browser snapshot is converted into parser-friendly HTML:

```python
well_details_snapshot_to_html(snapshot)
```

After that conversion, the same parser can extract the fields.

So the strategy mapping is:

```text
Strategy 1: active browser session
  Firecrawl role: remote live browser
  Python client: FirecrawlBrowserSessionWellDetailsClient
  Firecrawl APIs used: /v2/browser and /v2/browser/{session_id}/execute
  Returned content: browser-visible snapshot converted to HTML

Strategy 2: normal scrape endpoint
  Firecrawl role: single-page scrape service
  Python client: FirecrawlWellDetailsClient
  Firecrawl API used: /v2/scrape
  Returned content: raw HTML / HTML
```

So Firecrawl is doing the external-web work:

- loading JavaScript-rendered pages
- using a browser-like environment
- keeping a persistent profile and cookies
- giving a human a live verification window
- returning either raw HTML or browser-visible text back to Python

Your local app is doing the data pipeline work:

- deciding which APIs to scrape
- building Well Details URLs
- choosing the Firecrawl strategy
- parsing returned content
- normalizing records
- writing CSV, checkpoint, and report files
- stopping safely when protected pages appear

The cleanest summary is:

```text
Python controls the scrape.
Firecrawl fetches the web page.
Parser extracts data.
Ingestion writes durable outputs.
```

Firecrawl is not the parser and not the database layer. It is the remote browser and scraping engine that gets page content into the Python pipeline.

## Full Flow Summary

```text
make scraping
  -> Makefile loads .env
  -> .venv/bin/python -m app.cli scrape-wells
  -> app/cli/__main__.py calls main()
  -> app/cli/commands.py parses CLI command
  -> scrape_wells_command()
  -> builds ScrapeConfig
  -> chooses Firecrawl client
  -> app/services/ingestion.py scrape_wells()
  -> reads API CSV
  -> reads checkpoint
  -> loops over API numbers
  -> builds WellDetails.aspx URL
  -> _scrape_one_api()
  -> client.scrape_html(url)
  -> Firecrawl fetches page or browser snapshot
  -> parser extracts fields
  -> normalize_record()
  -> write CSV, checkpoint, and report
```