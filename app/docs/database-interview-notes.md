# Database Interview Notes

## Purpose

The project uses a local SQLite database to store normalized New Mexico well
data after scraping and cleanup. The database is the stable boundary between
the ingestion pipeline and the FastAPI service:

```text
scraping/loading path
  -> creates or refreshes api_well_data.db

API path
  -> reads api_well_data.db
  -> does not scrape or write records during requests
```

The main table is `api_well_data`. It stores one normalized record per well,
keyed by API number.

## Why SQLite

SQLite fits this assignment because the data set is local, structured, and
read-heavy. It avoids a separate database server while still supporting the
needed schema, indexes, upserts, and read queries.

For a larger production system, PostgreSQL with PostGIS would be a natural next
step, especially for concurrent writes or native geospatial indexing.

## Table Shape

The database table uses the assignment column names directly, such as:

```text
"API"
"Operator"
"Latitude"
"Longitude"
"Well Type"
"Directional Status"
```

The load path normalizes scraped/source records into this exact shape before
inserting them. The API can then return stable field names without repairing
full records on every request.

## Primary Key And Upserts

`"API"` is the primary key because the API number uniquely identifies a well in
this data set.

The loader uses an upsert:

```text
new API number      -> insert row
existing API number -> update row
```

This is useful even though the HTTP API is read-only. Writes happen through the
CLI load path, not through POST or PATCH routes.

Why it matters:

- rerunning `make load-db` does not create duplicate rows
- corrected scrape output can update existing wells
- resumed or repeated ingestion stays one row per API number
- the loader can safely refresh the same database

## Numeric Coordinates

Latitude and longitude are stored as numeric values, not strings, because the
polygon endpoint uses range comparisons:

```sql
"Latitude" BETWEEN ? AND ?
"Longitude" BETWEEN ? AND ?
```

Numeric storage avoids string-comparison bugs and lets SQLite correctly filter
candidate wells by coordinate bounds.

Rows with missing coordinates are excluded from polygon candidate searches
because they cannot be placed geographically.

## Coordinate Index

The table has a composite index on latitude and longitude:

```sql
CREATE INDEX IF NOT EXISTS idx_api_well_data_lat_lon
    ON api_well_data ("Latitude", "Longitude");
```

This supports the polygon endpoint. The search uses two steps:

```text
1. SQLite does a fast bounding-box candidate search.
2. Python/Shapely checks exact polygon coverage.
```

SQLite handles the cheap range filtering. Shapely handles the accurate
point-in-polygon geometry.

Without the index, SQLite may need to scan the whole table for every polygon
request. With the index, it can narrow candidate rows more efficiently.

## API Numbers As Text

API numbers are identifiers, not values used for arithmetic. Storing them as
text avoids numeric formatting issues and preserves leading zeroes if they
appear.

The public API accepts hyphenated or digit-only formats, but the lookup key is
digit-only:

```text
30-015-25325 -> 3001525325
```

## Read-Only API Access

The API opens SQLite through read-only helpers. That separation keeps the
system easy to reason about:

```text
CLI commands
  -> create or refresh the database

API routes
  -> read from the database
```

This prevents accidental writes from web requests and makes testing easier
because the write path and read path can be exercised independently.

## Useful Interview Answers

**Why did you index latitude and longitude?**

Because polygon search first filters wells by the polygon's bounding box. The
latitude/longitude index makes that range filter faster than scanning every
row.

**Why not do the whole polygon search in SQLite?**

SQLite does not provide full polygon operations by default. The project keeps
SQLite simple for storage and range filtering, then uses Shapely for accurate
geometry.

**Why use API as the primary key?**

The API number uniquely identifies a well. Using it as the primary key prevents
duplicates and lets ingestion safely upsert records when the scraper or loader
is rerun.

**Why have upsert if the API is read-only?**

The HTTP API is read-only, but the CLI loader still writes data into SQLite.
Upsert belongs to that load path. It lets the loader insert new wells and
update existing wells without duplicate primary-key rows.

**Why use SQLite instead of PostgreSQL?**

SQLite keeps the assignment easy to run locally while still demonstrating
schema design, indexes, upserts, and read queries. PostgreSQL/PostGIS would be
better if the project needed large-scale data, concurrent writes, or native
spatial indexes.

**What would you improve next?**

For production, I would consider database migrations for schema changes,
PostgreSQL/PostGIS for spatial queries, and stricter validation/reporting during
the load step.
