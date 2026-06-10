# SynMax Python Take-Home

This repository is for the SynMax Python developer take-home project.

The project will be built step by step:

1. Load New Mexico oil and gas well data for the provided API numbers into SQLite.
2. Serve that data through a small Python API.
3. Generate the required polygon-search CSV.

The canonical architecture and five-day build roadmap lives here:

```text
docs/SynMax_Takehome_Architecture_Plan.md
```

Part 1 ingestion has started. The current implementation can normalize a local source/export CSV,
filter it to the assignment API numbers, and load the exact required `api_well_data` table into
SQLite.

```bash
python -m app.cli load-db \
  --api-csv apis_pythondev_test.csv \
  --source-csv data/nm_ocd_expanded_export.csv \
  --database sqlite.db
```

The source/export CSV should contain NM OCD expanded-results-style headers such as `API`,
`Current Operator`, `Status`, `Type`, `Work Type`, `Latitude`, and `Longitude`.

## Running the API

Part 2 exposes the SQLite data through a read-only FastAPI service. The API expects the database
table to be named `api_well_data` and the stored `API` values to be digit-only text.

```bash
make start
```

The API requires `SYNMAX_DATABASE_PATH` in the process environment. You can keep that value in
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
- httpx
- lxml
- Shapely
- pytest
- ruff

## Current Status

Step 1 has the database schema, field normalization, and local CSV-to-SQLite loader in place. Step
2 has a read-only FastAPI service for health checks, single-well lookup, and polygon search. The
live source acquisition adapter and enrichment fields will be added in later steps.
