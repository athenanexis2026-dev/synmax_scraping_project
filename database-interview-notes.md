# Database Interview Notes

## Purpose

The project uses a local SQLite database to store normalized New Mexico well data after it has been scraped and cleaned. The database is the stable boundary between the ingestion pipeline and the FastAPI service: scraping can be slow, protected by browser checks, and dependent on the external NM OCD site, while the API needs fast and predictable reads.

The main database table is `api_well_data`. It stores one normalized record per well, keyed by API number.

## Why SQLite

SQLite is a good fit for this project because the data set is local, structured, and read-heavy. The API does not need a separate database server to demonstrate the required functionality, and SQLite keeps the setup simple for development, testing, and interview review.

The project still treats SQLite like a real persistence layer:

- schema creation is centralized in the repository layer
- data is loaded through a repeatable CLI command
- records are normalized before insertion
- API routes use read-only database connections
- tests cover table creation, upserts, lookups, and geospatial filtering

## Primary Key And Upserts

The API number is used as the primary identifier for a well. That matters because the scraper or loader may see the same well more than once across runs. Instead of blindly appending duplicates, the load path uses an upsert:

- new API numbers are inserted
- existing API numbers are updated
- the database remains one row per well

This also makes the ingestion process safer to rerun after a scrape is resumed or corrected.

## Why Latitude And Longitude Are Indexed

I added a composite index on latitude and longitude because the API supports polygon searches. A polygon search first calculates the polygon's bounding box, then asks SQLite for wells whose coordinates fall inside that latitude/longitude range.

The index helps SQLite narrow the candidate rows before Python does the more precise polygon check with Shapely. Without the index, SQLite may need to scan the whole well table for every polygon request. With the index, the database can more efficiently filter by coordinate range, which is especially useful as the number of wells grows.

The polygon search uses a two-step strategy:

1. SQLite performs a fast bounding-box prefilter using latitude and longitude.
2. Python/Shapely checks whether each candidate point is actually inside or on the boundary of the polygon.

This is a practical compromise: SQLite handles the cheap range filtering, and Shapely handles the accurate geospatial geometry.

## Why Store Coordinates As Numeric Values

Latitude and longitude are stored as numeric values, not strings, because the API compares them using range queries. Numeric storage avoids string-comparison bugs and allows queries such as "between minimum latitude and maximum latitude" to behave correctly.

Rows with missing coordinates are excluded from polygon candidate searches because they cannot be placed geographically.

## Data Normalization Before Loading

The scraper receives data from an external website, so the raw labels and values are not trusted as database-ready. Before records are inserted, the normalizer:

- maps source labels into the project's expected field names
- converts API numbers to digit-only text
- converts numeric fields into integers or floats
- converts empty strings into `NULL`
- builds a surface-location string when the source provides location parts separately
- keeps missing source data as missing instead of inventing values

This keeps the database consistent even if the scraper input comes from slightly different source labels or CSV exports.

## Why API Numbers Are Stored As Text

API numbers are identifiers, not values used for arithmetic. Storing them as text avoids accidental numeric formatting issues and preserves leading zeroes if they appear. The project normalizes API inputs by removing hyphens and keeping only digits, so both route input and database lookup use the same representation.

## Read-Only API Access

The FastAPI routes open SQLite in read-only mode. This is intentional because the running API should only serve data; ingestion and database loading happen through CLI commands.

That separation helps prevent accidental writes from web requests and makes the application easier to reason about:

- CLI commands create or refresh the database
- API routes read from the database
- tests can exercise both paths independently

## Caching Strategy

The service caches repeated well lookups and polygon searches in memory. The database file's modified time is part of the cache key, so when the SQLite file is replaced or reloaded, cached results are naturally invalidated.

The API also returns HTTP cache headers and ETags, which lets clients avoid downloading the same response again when nothing has changed.

## Schema Compatibility

The repository layer has compatibility helpers for selecting columns. It can read either the assignment-style column names or snake_case aliases. This makes the API more tolerant if an older or alternate database file is used during development.

The project-created database still uses the assignment's expected table shape, but the compatibility layer makes local testing and migration less fragile.

## Data Quality

The database reflects the source data after normalization. If the official well page does not provide a value, the project stores it as `NULL`. The scrape report tracks missing values, blocked pages, failed parses, and missing API numbers so data quality can be reviewed before or after loading.

This is important in an interview because it shows the project distinguishes between:

- data collection problems
- missing source data
- normalization problems
- API query behavior

## Useful Interview Answers

**Why did you index latitude and longitude?**

Because polygon search needs to find wells in a geographic area. The app first filters by the polygon's bounding box using latitude and longitude, and the index makes that range filter faster than scanning every row.

**Why not do the whole polygon search in SQLite?**

SQLite by itself does not provide full geospatial polygon operations unless extensions are added. I kept the database dependency simple and used SQLite for the efficient prefilter, then Shapely for accurate point-in-polygon logic.

**Why use API as the primary key?**

The API number uniquely identifies a well in this data set. Using it as the primary key prevents duplicates and allows ingestion to safely upsert records when the scraper is rerun.

**Why use SQLite instead of PostgreSQL?**

For this assignment, SQLite keeps the project easy to run locally while still supporting the needed schema, indexing, upserts, and read queries. If the data grew much larger or needed concurrent writes, PostgreSQL with PostGIS would be a natural next step.

**How do you keep bad scraped data out of the database?**

The project normalizes records before insertion, converts values to the expected types, filters to the requested API numbers, and records scrape failures separately. Missing source values stay `NULL` instead of being guessed.

**How does the API avoid modifying the database?**

The web service opens SQLite with a read-only connection. Writes are handled by CLI ingestion commands, not by API routes.

**What would you improve next?**

For a larger production version, I would consider PostgreSQL/PostGIS for native spatial indexes and polygon queries, database migrations for schema changes, and stronger source-data validation before load.
