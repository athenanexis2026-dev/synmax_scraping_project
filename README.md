# SynMax Python Take-Home

This repository is for the SynMax Python developer take-home project.

The project will be built step by step:

1. Load New Mexico oil and gas well data for the provided API numbers into SQLite.
2. Serve that data through a small Python API.
3. Generate the required polygon-search CSV.

Part 1 ingestion scrapes the official NM OCD Well Details pages for the provided API numbers,
normalizes the fields, and loads the exact required `api_well_data` table into SQLite.

```bash
cp .env.example .env
```

Add your Firecrawl key to `.env` once. Keep `.env` local; it is ignored by git.

Before the first full scrape, verify the persistent Firecrawl browser profile against the protected
NM OCD site:

```bash
make open-session
```

Open the interactive Firecrawl URL printed by that command. If the official page shows a
Cloudflare/Turnstile challenge, complete it there and wait until the real Well Details data is
visible. Keep that session open and confirm the scraper can parse through the same live browser:

```bash
make check-session
```

If `make check-session` confirms it can parse one well, run the ingestion while the browser session
is still open. After ingestion finishes, close the session.

```bash
make scraping
make load-db
make close-session
```

Or run the whole ingestion:

```bash
make ingest
```

The scraper uses Firecrawl's single-page scrape endpoint with a named browser profile, so a
verified profile can preserve cookies/session state for the protected NM OCD pages. It writes:

- `data/api_well_data_scraped.csv`
- `data/scrape_report.json`
- `data/scrape_checkpoint.json`

If protected pages are returned instead of well data, the scraper stops after repeated blocks and
reports those APIs instead of guessing values. Rerun `make open-session`, complete the challenge,
keep the session open, and retry `make ingest`; the checkpoint allows the scraper to resume.

## Running the API

Part 2 exposes the SQLite data through a read-only FastAPI service. The API expects the database
table to be named `api_well_data` and the stored `API` values to be digit-only text.

```bash
make start
```

The API uses `SYNMAX_DATABASE_PATH` from the process environment. You can keep that value in
`.env`, and `make start` will load it before starting the API:

```bash
SYNMAX_DATABASE_PATH=/absolute/path/to/api_well_data.db
```

For local development, use:

```bash
make start
```

Keep `.env.example` as the shareable template and use `.env` for your local machine path.

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Single-well lookup:

```bash
curl http://127.0.0.1:8000/well/30-015-25325
```

The public route requires a hyphenated API number like `30-015-25325`. Internally, it normalizes
that value to `3001525325` to match the SQLite table.

Polygon search:

```bash
curl 'http://127.0.0.1:8000/wells/polygon?points=32.81,-104.19;32.66,-104.32;32.54,-104.24;32.50,-104.03;32.73,-104.01;32.79,-103.91;32.84,-104.05;32.81,-104.19'
```

The polygon endpoint accepts ordered `lat,lon` pairs. At least three distinct points are required
because a polygon is a closed area; two points define only a line. The API validates coordinate
ranges, closes the polygon when needed, prefilters candidate rows with the latitude/longitude
index, and then uses exact Shapely geometry matching. Wells on the polygon boundary are included.

Successful read responses include `Cache-Control: public, max-age=300` and an `ETag`, so repeated
requests can use standard HTTP caching.

## Planned Stack

- Python 3.11+
- SQLite
- FastAPI
- Uvicorn
- Shapely
- pytest
- ruff

## Current Status

Step 1 has single-source Well Details scraping, field normalization, checkpointing, reporting, and
SQLite loading in place. Step 2 has a read-only FastAPI service for health checks, single-well
lookup, and polygon search.
