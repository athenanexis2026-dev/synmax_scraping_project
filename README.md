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

Step 1 has the database schema, field normalization, and local CSV-to-SQLite loader in place. The
live source acquisition adapter and enrichment fields will be added in later steps.
