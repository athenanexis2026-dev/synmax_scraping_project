# SynMax API Flow

This document explains how the API works across every layer of the project:
startup, routes, validation, normalization, caching, repository access,
database structure, and the ingestion flow that prepares data before the API
serves it.

The most important idea is that this project has two big flows:

1. Data preparation flow: scrape -> parse -> normalize -> load SQLite.
2. Runtime API flow: receive HTTP request -> validate -> normalize request input
   -> query cached SQLite data -> return cached HTTP response.

The API does not scrape live data when someone calls `/well/...`. It only reads
already-normalized data from SQLite.

## High-Level Architecture

```text
Client request
  -> FastAPI app
  -> route layer
  -> request validation
  -> request normalization
  -> service layer
  -> process-level cache
  -> repository layer
  -> read-only SQLite query
  -> response cache helper
  -> JSON response
```

The background data-preparation flow is separate:

```text
API CSV
  -> CLI command
  -> Firecrawl fetch/browser session
  -> NM OCD Well Details HTML or browser snapshot
  -> parser
  -> normalization
  -> scraped CSV/checkpoint/report
  -> load-db
  -> SQLite api_well_data table
```

## Layer 1: App Startup

Main file: `app/main.py`

The API starts from the module-level object:

```python
app = create_app()
```

`create_app()` builds the FastAPI application:

```text
create_app()
  -> create FastAPI app with OpenAPI metadata
  -> read SYNMAX_DATABASE_PATH from the environment
  -> store database path in api.state.database_path
  -> register custom validation error handler
  -> include health router
  -> include wells router
```

The database path comes from:

```text
SYNMAX_DATABASE_PATH
```

That environment variable is required. If it is missing, the app cannot know
which SQLite file to serve.

The app stores the path here:

```python
api.state.database_path = get_database_path()
```

Routes later access the same path through:

```python
request.app.state.database_path
```

This is a clean design because the route functions do not need to read
environment variables directly. The app is configured once at startup, and all
routes use the configured state.

## Layer 2: Route Layer

Main file: `app/api/routes/wells.py`

The route layer is the public HTTP surface. Its responsibilities are:

- Define which URLs exist.
- Define which path/query parameters are accepted.
- Call the correct service-layer function.
- Convert domain errors into HTTP errors.
- Return the final response shape.

This project has three main public endpoints:

- `GET /health`
- `GET /well/{api_number}`
- `GET /wells/polygon?points=...`

## Route: GET /health

Main file: `app/api/routes/health.py`

Purpose: confirm the API is running and the configured database is reachable.

Flow:

```text
client calls /health
  -> route reads database_path from request.app.state
  -> opens SQLite in read-only mode
  -> runs SELECT 1 FROM api_well_data LIMIT 1
  -> closes connection
  -> returns {"status": "ok", "database": "connected"}
```

Success response:

```json
{
  "status": "ok",
  "database": "connected"
}
```

Error behavior:

- If the database cannot be opened or queried, the route returns `503`.
- The route does not return table counts or application metadata. It only checks
  readiness.

## Route: GET /well/{api_number}

Main file: `app/api/routes/wells.py`

Purpose: return one well record by API number.

Example:

```text
GET /well/30-015-25325
```

Accepted API number formats:

```text
30-015-25325
3001525325
30-015-45678-0000
30015456780000
```

Detailed flow:

```text
FastAPI receives GET /well/30-015-25325
  -> route is matched to read_well()
  -> FastAPI validates api_number against the configured regex pattern
  -> route calls normalize_hyphenated_api_number(api_number)
  -> "30-015-25325" becomes "3001525325"
  -> route reads database_path from request.app.state
  -> route calls read_cached_well(database_path, "3001525325")
  -> service checks process-level LRU cache
  -> on cache miss, service opens SQLite read-only
  -> repository queries api_well_data WHERE API = ?
  -> repository returns row as dict or None
  -> service closes DB connection
  -> route returns 404 if row is None
  -> route passes row into json_cache_response()
  -> response gets Cache-Control and ETag headers
  -> response is returned to client
```

Important behavior:

- Public API numbers can be hyphenated or digit-only.
- Database API numbers are stored digit-only.
- The route normalizes the public input before lookup.
- A well-formed API number that does not exist returns `404`.
- A malformed API number returns `422`.
- Database availability problems return `503`.

Example normalization:

```text
30-015-25325       -> 3001525325
3001525325         -> 3001525325
30-015-45678-0000 -> 30015456780000
30015456780000    -> 30015456780000
```

## Route: GET /wells/polygon

Main file: `app/api/routes/wells.py`

Purpose: return API numbers for wells whose coordinates are inside or on the
boundary of a polygon.

Example:

```text
GET /wells/polygon?points=32,-105;33,-105;33,-104;32,-104
```

The response shape is:

```json
{
  "api_numbers": ["3001525325", "3001525326"],
  "count": 2
}
```

Detailed flow:

```text
FastAPI receives GET /wells/polygon?points=...
  -> route is matched to wells_in_polygon()
  -> FastAPI reads the required points query parameter
  -> route reads database_path from request.app.state
  -> route calls read_cached_polygon_api_numbers(database_path, points)
  -> service checks process-level LRU cache
  -> on cache miss, service validates/parses the polygon
  -> service calculates polygon bounding box
  -> repository asks SQLite for wells inside the bounding box
  -> service uses Shapely for exact polygon coverage check
  -> service sorts matching API numbers
  -> route returns {"api_numbers": api_numbers, "count": len(api_numbers)}
  -> response gets Cache-Control and ETag headers
```

Error behavior:

- Missing `points` returns `422`.
- Malformed `points` returns `422`.
- Invalid polygons return `422`.
- Database availability problems return `503`.

## Layer 3: API Number Validation

Main file: `app/schemas/wells.py`

The route-level API number pattern is:

```python
API_NUMBER_PATTERN_TEXT = r"^(?:\d{10}(?:\d{4})?|\d{2}-\d{3}-\d{5}(?:-\d{4})?)$"
```

This allows:

```text
10 digit API:
  3001525325

10 digit API, hyphenated:
  30-015-25325

14 digit API:
  30015456780000

14 digit API, hyphenated:
  30-015-45678-0000
```

This rejects values such as:

```text
30015
30-15-25325
abc
30-015-25325-extra
30-015
```

After validation, the API number is normalized:

```python
return api_number.replace("-", "")
```

That means hyphens are removed, but digits are otherwise preserved.

The error message is intentionally human-readable:

```text
api_number must use one of these formats: 30-015-25325, 3001525325,
30-015-45678-0000, or 30015456780000
```

## Custom Validation Error Handler

Main file: `app/main.py`

FastAPI normally returns a verbose validation error object. This project
customizes validation errors for the `api_number` path parameter.

Flow:

```text
FastAPI detects RequestValidationError
  -> readable_validation_exception_handler() receives the error
  -> handler loops over validation errors
  -> if the error location is ("path", "api_number")
      -> return {"detail": API_NUMBER_ERROR} with status 422
  -> otherwise use FastAPI's default validation handler
```

This keeps `/well/{api_number}` errors simple for public API users, while
leaving other FastAPI validation errors unchanged.

## Layer 4: Polygon Validation

Main file: `app/utils/geo.py`

The polygon endpoint accepts a string of semicolon-separated coordinate pairs:

```text
lat,lon;lat,lon;lat,lon
```

Example:

```text
32,-105;33,-105;33,-104;32,-104
```

Validation rules:

- `points` is required.
- The string cannot be empty or only whitespace.
- There cannot be empty coordinate pairs.
- Each pair must contain exactly two values.
- Each pair must use the format `lat,lon`.
- Latitude and longitude must be numeric.
- Latitude and longitude must be finite numbers.
- Latitude must be between `-90` and `90`.
- Longitude must be between `-180` and `180`.
- At least three distinct coordinate pairs are required.
- The polygon is closed automatically if the first and last point differ.
- Self-intersecting polygons are rejected.
- Zero-area polygons are rejected.

Important coordinate detail:

The API accepts coordinates as:

```text
latitude,longitude
```

Shapely geometry expects:

```text
x,y
```

For geographic coordinates, `x,y` means:

```text
longitude,latitude
```

So this API input:

```text
32,-105
```

becomes this Shapely coordinate:

```python
(-105, 32)
```

Boundary behavior:

```python
polygon.covers(Point(longitude, latitude))
```

The use of `covers()` means a well on the polygon boundary is included.

## Layer 5: Service Layer

Main file: `app/services/well_queries.py`

The service layer sits between routes and repositories. It coordinates:

- Database modified-time lookup for cache invalidation.
- Process-level LRU caching.
- Read-only SQLite connections.
- Polygon parsing and exact geospatial filtering.
- Sorting final API number results.

The route layer does not directly open SQLite. It asks the service layer.

## Service Flow: Single Well Lookup

Public service function:

```python
read_cached_well(database_path, normalized_api)
```

Detailed flow:

```text
read_cached_well(database_path, normalized_api)
  -> database_mtime_ns(database_path)
      -> reads database_path.stat().st_mtime_ns
      -> raises DatabaseUnavailable if file cannot be stat'ed
  -> calls _cached_get_well(str(database_path), database_mtime_ns, normalized_api)
```

The cached function:

```python
@lru_cache(maxsize=512)
def _cached_get_well(database_path, database_mtime_ns, normalized_api):
```

Detailed cache-miss flow:

```text
_cached_get_well(...)
  -> opens read-only SQLite connection
  -> calls get_well(connection, normalized_api)
  -> closes connection in finally block
  -> returns dict or None
```

The parameter `database_mtime_ns` is not used inside the function body. It is
included so it becomes part of the LRU cache key. When the database file changes,
the modified time changes, which creates a new cache key.

## Service Flow: Polygon Lookup

Public service function:

```python
read_cached_polygon_api_numbers(database_path, points)
```

Detailed flow:

```text
read_cached_polygon_api_numbers(database_path, points)
  -> database_mtime_ns(database_path)
  -> calls _cached_polygon_api_numbers(str(database_path), database_mtime_ns, points)
```

The cached function:

```python
@lru_cache(maxsize=128)
def _cached_polygon_api_numbers(database_path, database_mtime_ns, points):
```

Detailed cache-miss flow:

```text
_cached_polygon_api_numbers(...)
  -> parse_polygon_points(points)
      -> validates input
      -> builds Shapely Polygon
      -> calculates min/max latitude and longitude
  -> opens read-only SQLite connection
  -> calls iter_wells_in_bounds(...)
      -> returns only wells inside bounding box
  -> closes connection
  -> loops over bounding-box candidates
  -> checks exact polygon coverage with point_is_covered_by_polygon()
  -> collects matching API numbers
  -> returns sorted API numbers
```

This two-step geospatial search is intentional:

1. SQLite performs a fast bounding-box filter.
2. Shapely performs the exact polygon check only on the smaller candidate set.

This avoids running Shapely checks on every row in the database.

## Layer 6: Repository Layer

Main file: `app/repositories/wells.py`

The repository layer owns direct SQL access. Its responsibilities are:

- Create/recreate the SQLite table.
- Upsert normalized records.
- Query one well by API.
- Query wells inside a lat/lon bounding box.
- Convert SQLite rows into dictionaries.
- Support both assignment-style and snake_case column names.

## Repository Flow: get_well()

Function:

```python
get_well(connection, api_number)
```

Detailed flow:

```text
get_well(connection, api_number)
  -> inspect table columns using PRAGMA table_info(api_well_data)
  -> build SELECT expressions for every assignment column
  -> find the correct API column name
      -> "API" if assignment-style schema exists
      -> "api" if snake_case schema exists
  -> run SELECT ... FROM api_well_data WHERE API = ?
  -> fetch one row
  -> return dict(row) if found
  -> return None if not found
```

The query uses a parameter:

```sql
WHERE "API" = ?
```

The API number value is passed separately:

```python
(api_number,)
```

This avoids directly interpolating user input into SQL.

## Repository Flow: iter_wells_in_bounds()

Function:

```python
iter_wells_in_bounds(
    connection,
    min_latitude,
    max_latitude,
    min_longitude,
    max_longitude,
)
```

Detailed flow:

```text
iter_wells_in_bounds(...)
  -> inspect table columns
  -> find API, Latitude, and Longitude columns
  -> SELECT API, Latitude, Longitude
  -> exclude rows where Latitude is NULL
  -> exclude rows where Longitude is NULL
  -> filter Latitude BETWEEN min_latitude AND max_latitude
  -> filter Longitude BETWEEN min_longitude AND max_longitude
  -> order by API
  -> return list of dicts
```

This function returns candidates, not final polygon matches. The final exact
polygon check happens in the service layer.

## Schema Compatibility

The repository can read both of these column styles:

```text
Assignment style:
  "Well Type"
  "Directional Status"
  "Single/Multiple Completion"

Snake case style:
  well_type
  directional_status
  completion_type
```

This mapping lives in `SNAKE_CASE_COLUMN_ALIASES`.

If an optional assignment column is missing, the repository can select:

```sql
NULL AS "Column Name"
```

That keeps the API response shape stable, even if a compatible database is
missing some optional columns.

## Layer 7: SQLite Schema

Main file: `app/repositories/schema.py`

The main table is:

```text
api_well_data
```

The assignment columns are:

```text
Operator
Status
Well Type
Work Type
Directional Status
Multi-Lateral
Mineral Owner
Surface Owner
Surface Location
GL Elevation
KB Elevation
DF Elevation
Single/Multiple Completion
Potash Waiver
Spud Date
Last Inspection
TVD
API
Latitude
Longitude
CRS
```

Important schema characteristics:

- `API` is `TEXT PRIMARY KEY NOT NULL`.
- `Latitude` and `Longitude` are `REAL`.
- `GL Elevation`, `KB Elevation`, `DF Elevation`, and `TVD` are `INTEGER`.
- Most descriptive fields are `TEXT`.

There is also a coordinate index:

```sql
CREATE INDEX IF NOT EXISTS idx_api_well_data_lat_lon
    ON api_well_data ("Latitude", "Longitude");
```

That index helps the polygon endpoint because its first database step is a
lat/lon bounding-box query.

## Layer 8: Normalization

Main file: `app/utils/normalize.py`

Normalization is one of the most important layers in the project. Its job is to
take messy source data and turn it into the exact shape expected by the
database and API.

The runtime API performs only small request normalization. The bigger
normalization happens during ingestion and database loading.

There are two kinds of normalization:

1. Public request normalization.
2. Source/data normalization before SQLite load.

## Public Request Normalization

This happens in `app/schemas/wells.py`.

For `/well/{api_number}`, the user can send:

```text
30-015-25325
```

The API normalizes it to:

```text
3001525325
```

That normalized value is used for the SQLite lookup.

This normalization is intentionally strict:

- It accepts only valid public API number formats.
- It does not attempt to repair malformed API numbers.
- It removes hyphens only after validation succeeds.

## Source/Data Normalization

This happens in `app/utils/normalize.py`.

The main function is:

```python
normalize_record(source_record)
```

Detailed flow:

```text
normalize_record(source_record)
  -> create a new record with every assignment column set to None
  -> for each assignment column:
      -> read source_record[column]
      -> clean/coerce the value
      -> store it
  -> for each source alias in FIELD_MAPPING:
      -> if the target field is still None:
          -> read source_record[source_field]
          -> clean/coerce it into target field
  -> if Surface Location is still None:
      -> build it from component location fields
  -> repair special Well Details fields
      -> Potash Waiver
      -> Spud Date
      -> Last Inspection
      -> TVD
  -> normalize API number to digits only
  -> return normalized record
```

The result always has the same keys as `ASSIGNMENT_COLUMNS`.

## Field Mapping

Source data can use different labels than the final database schema. The
normalizer maps those labels into the assignment columns.

Examples:

```text
Current Operator      -> Operator
Type                  -> Well Type
Direction             -> Directional Status
Single / Multi Compl  -> Single/Multiple Completion
True Vertical Depth   -> TVD
Elevation             -> GL Elevation
Kelly Bushing         -> KB Elevation
Drilling Floor        -> DF Elevation
Projection            -> CRS
Lat / Long CRS        -> CRS
```

Important rule:

Exact assignment columns win over aliases.

Example:

```text
source has Operator = "Assignment Operator"
source has Current Operator = "Export Operator"
```

The result keeps:

```text
Operator = "Assignment Operator"
```

The alias is used only if the target field is still `None`.

## Type Coercion

The normalizer converts source strings into useful Python values before they are
written into SQLite.

General cleanup:

```text
None         -> None
""           -> None
"   "        -> None
" text "     -> "text"
```

Integer columns:

```text
GL Elevation
KB Elevation
DF Elevation
TVD
```

Integer coercion examples:

```text
"10,250" -> 10250
"3210.0" -> 3210
"abc"    -> None
```

Real/float columns:

```text
Latitude
Longitude
```

Float coercion examples:

```text
"32.75"   -> 32.75
"-104.05" -> -104.05
"abc"     -> None
```

Other columns remain cleaned strings.

## API Number Normalization In Source Records

Function:

```python
normalize_api_number(value)
```

Behavior:

```text
None              -> None
""                -> None
"30-015-12345"    -> "3001512345"
" 3001512345 "    -> "3001512345"
"API: 30-015..."  -> digits only from the string
```

The function extracts digits and joins them together. This preserves leading
zeroes if they exist in the source text.

## Surface Location Normalization

If `Surface Location` is missing, the normalizer tries to build it from smaller
fields.

Fields used:

```text
Unit Letter
Section
Township
Range
OCD Unit Letter
Footages
Footage NS
NS Indicator
Footage EW
EW Indicator
```

Example source:

```text
Section = 12
Township = 18S
Range = 29E
```

Normalized result:

```text
Surface Location = "Section: 12; Township: 18S; Range: 29E"
```

## Potash Waiver Repair

Function:

```python
_coerce_yes_no(value)
```

Behavior:

```text
"Yes something..." -> "Yes"
"No something..."  -> "No"
None               -> None
text with ":" and no yes/no prefix -> None
other clean text -> same text
```

This protects the database from storing long neighboring scraped text in a
field that is expected to be a simple yes/no style value.

## Date Repair

Function:

```python
_coerce_date(value, require_leading=False)
```

The normalizer looks for valid dates in this format:

```text
MM/DD/YYYY
```

For `Spud Date`, it can extract the first valid date anywhere in the value.

For `Last Inspection`, it requires the date to appear at the beginning of the
value. This is intentional because some scraped text can include nearby dates
from unrelated fields.

Example:

```text
Last Inspection = "Current APD Expiration: 01/01/1902 ..."
```

This becomes:

```text
Last Inspection = None
```

because the date is not actually at the start of the Last Inspection value.

## TVD Repair

If `TVD` is missing, the normalizer searches all source text for:

```text
True Vertical Depth: <number>
```

Example:

```text
True Vertical Depth: 5502
```

Normalized result:

```text
TVD = 5502
```

This is useful because TVD can sometimes appear inside a larger scraped text
block instead of as a clean standalone field.

## Record List Normalization

Function:

```python
normalize_records(source_records, api_numbers=None)
```

Detailed flow:

```text
normalize_records(...)
  -> loop over source records
  -> normalize each record
  -> skip records without API
  -> if api_numbers filter is provided:
      -> skip records not in requested API set
  -> sort final records by API
  -> return list
```

This is used by `load-db` to make sure only requested APIs are loaded.

## Layer 9: Scrape And Parse Before Normalization

Main files:

- `app/services/ingestion.py`
- `app/services/well_details/clients.py`
- `app/services/well_details/parser.py`
- `app/services/well_details/urls.py`

The API is read-only, but the database must be created from scraped source
data. That happens through the CLI and ingestion services.

## URL Building

Main file: `app/services/well_details/urls.py`

The official NM OCD Well Details URL format is:

```text
https://wwwapps.emnrd.nm.gov/OCD/OCDPermitting/Data/WellDetails.aspx?api={api}
```

The helper accepts digit-only or hyphenated API numbers and converts them to
NM OCD's public hyphenated format.

Examples:

```text
3001525325       -> 30-015-25325
30015456780000   -> 30-015-45678-0000
```

## Firecrawl Client Layer

Main file: `app/services/well_details/clients.py`

There are three client classes:

1. `FirecrawlWellDetailsClient`
2. `FirecrawlBrowserClient`
3. `FirecrawlBrowserSessionWellDetailsClient`

`FirecrawlWellDetailsClient` calls Firecrawl's scrape endpoint:

```text
POST https://api.firecrawl.dev/v2/scrape
```

It requests:

```text
html
rawHtml
```

It also:

- Uses a browser-like user agent.
- Disables `onlyMainContent`.
- Sets a wait time.
- Uses proxy mode.
- Disables Firecrawl cache storage.
- Optionally uses a named Firecrawl profile.

`FirecrawlBrowserClient` manages browser sessions:

```text
POST /browser
POST /browser/{session_id}/execute
DELETE /browser/{session_id}
```

`FirecrawlBrowserSessionWellDetailsClient` uses an already-open browser session:

```text
agent-browser open <url>
sleep
agent-browser snapshot
```

It converts the browser accessibility snapshot into parser-friendly HTML.

## Parser Layer

Main file: `app/services/well_details/parser.py`

The parser turns Well Details HTML into a partial source record.

Flow:

```text
parse_well_details_html(html_text, expected_api)
  -> detect protected/challenge page
  -> parse label/value spans from HTML
  -> require Operator or Status to prove real data exists
  -> map labels to assignment columns
  -> clean operator field
  -> parse Lat / Long into Latitude, Longitude, CRS
  -> extract API from hidden input or title text
  -> fallback to expected_api
  -> return parsed record
```

Label mapping examples:

```text
Operator              -> Operator
Status                -> Status
Well Type             -> Well Type
Direction             -> Directional Status
Multi-Lateral         -> Multi-Lateral
Single / Multi Compl  -> Single/Multiple Completion
True Vertical Depth   -> TVD
Lat / Long            -> Latitude, Longitude, CRS
```

Protected page detection looks for content such as:

```text
Cloudflare
Turnstile
Just a moment
Verification failed
```

If protection content appears without real well data, the parser raises
`ProtectedPageError`.

If normal Well Details labels are missing, it raises `WellDetailsParseError`.

## Ingestion Loop

Main file: `app/services/ingestion.py`

Function:

```python
scrape_wells(config, client)
```

Detailed flow:

```text
scrape_wells(config, client)
  -> read requested API numbers from CSV
  -> read checkpoint if resume is enabled
  -> loop over sorted API numbers
      -> skip APIs already completed in checkpoint
      -> build official Well Details URL
      -> scrape one API
          -> client.scrape_html(url)
          -> parse_well_details_html(html, expected_api)
          -> normalize_record(parsed_record)
      -> on success:
          -> store record in checkpoint["completed"]
          -> clear previous blocked/failure entry for that API
      -> on protected page:
          -> store in checkpoint["blocked"]
          -> maybe stop after threshold
      -> on scrape/browser/parse/value error:
          -> store in checkpoint["failures"]
          -> maybe stop after threshold
      -> persist outputs after each API
      -> sleep between requests
  -> persist final outputs
  -> return report
```

Outputs:

```text
data/api_well_data_scraped.csv
data/scrape_checkpoint.json
data/scrape_report.json
```

The checkpoint lets the scraper resume instead of starting from zero after a
blocked or failed page.

The report includes:

- Requested count.
- Scraped count.
- Blocked count.
- Failed count.
- Missing APIs.
- Parse failures.
- Remaining null columns.
- Stopped reason.

## Database Loading

Main file: `app/cli/commands.py`

Command:

```text
python -m app.cli load-db
```

Makefile command:

```text
make load-db
```

Detailed flow:

```text
load_database_command(args)
  -> read requested API numbers from args.api_csv
  -> read source records from scraped CSV
  -> normalize records again
  -> filter to requested API numbers
  -> open SQLite write connection
  -> if --replace:
      -> drop and recreate api_well_data
     else:
      -> initialize table if needed
  -> upsert normalized records
  -> close connection
```

The project normalizes again during `load-db` even though scraping already
normalizes. This makes loading safer because it can also load from a CSV that
was edited or produced elsewhere.

## Upsert Behavior

Main file: `app/repositories/wells.py`

Function:

```python
upsert_wells(connection, records)
```

Detailed flow:

```text
upsert_wells(...)
  -> build INSERT statement for all assignment columns
  -> use API as primary key
  -> ON CONFLICT("API") DO UPDATE
  -> insert new rows
  -> replace existing rows with same API
  -> commit transaction
  -> return number of rows loaded
```

Because `API` is the primary key, reloading the same API updates the existing
record instead of creating duplicates.

## Layer 10: Caching

There are two caching layers:

1. Server-side process cache.
2. HTTP response cache.

These solve different problems.

The server-side cache helps the API avoid repeated database reads and repeated
Shapely polygon checks.

The HTTP cache helps clients avoid downloading unchanged JSON responses.

## Server-Side LRU Cache

Main file: `app/services/well_queries.py`

Single-well cache:

```python
@lru_cache(maxsize=512)
def _cached_get_well(database_path, database_mtime_ns, normalized_api):
```

Polygon cache:

```python
@lru_cache(maxsize=128)
def _cached_polygon_api_numbers(database_path, database_mtime_ns, points):
```

The cache key for a well lookup is effectively:

```text
database path + database modified time + normalized API number
```

The cache key for a polygon lookup is effectively:

```text
database path + database modified time + raw points string
```

The database modified time comes from:

```python
database_path.stat().st_mtime_ns
```

This means:

```text
same DB file + same API number -> cache hit
same DB file + same polygon string -> cache hit
DB file changes -> modified time changes -> cache miss
```

The code does not manually clear the old cache entries. Instead, changing the
database modified time naturally creates a new cache key. Old entries remain in
the LRU cache until evicted, but they are no longer used for current database
state.

Single-well cache size:

```text
512 entries
```

Polygon cache size:

```text
128 entries
```

Polygon cache size is smaller because polygon results can represent more work
and potentially larger result sets.

## HTTP Response Cache

Main file: `app/api/cache.py`

Successful read responses are passed through:

```python
json_cache_response(content, request)
```

This function:

```text
builds an ETag from the JSON content
adds Cache-Control header
adds ETag header
checks If-None-Match from the request
returns 304 if the ETag matches
otherwise returns full JSON response
```

The cache-control value is:

```text
public, max-age=300
```

That tells clients and browsers that the response can be cached for 300
seconds.

The ETag is built by:

```text
JSON serialize content with sorted keys
  -> SHA-256 hash
  -> quote the digest
```

Example:

```text
ETag: "abc123..."
```

Client revalidation flow:

```text
first request:
  -> client gets full JSON response
  -> client stores ETag

second request:
  -> client sends If-None-Match: "<etag>"
  -> API rebuilds ETag for current content
  -> if ETag matches:
      -> return 304 Not Modified
  -> if ETag differs:
      -> return full JSON response with new ETag
```

This is useful for dashboards, frontends, scripts, and map views that may
request the same well or polygon repeatedly.

## Complete Runtime Flow: /well/{api_number}

```text
HTTP GET /well/30-015-25325
  -> FastAPI matches /well/{api_number}
  -> FastAPI validates api_number using API_NUMBER_PATTERN_TEXT
  -> custom validation handler formats API-number errors
  -> read_well() receives api_number
  -> normalize_hyphenated_api_number()
      -> validates again
      -> removes hyphens
      -> returns 3001525325
  -> read database path from request.app.state.database_path
  -> read_cached_well(database_path, "3001525325")
      -> read database modified time
      -> check LRU cache
      -> on miss:
          -> open SQLite read-only
          -> get_well(connection, "3001525325")
              -> inspect table columns
              -> build stable SELECT list
              -> query WHERE API = ?
              -> return dict(row) or None
          -> close SQLite connection
  -> if result is None:
      -> raise HTTPException(404, "Well not found")
  -> json_cache_response(well, request)
      -> build ETag from response content
      -> add Cache-Control and ETag
      -> if If-None-Match matches:
          -> return 304
      -> else:
          -> return JSON response
```

## Complete Runtime Flow: /wells/polygon

```text
HTTP GET /wells/polygon?points=32,-105;33,-105;33,-104;32,-104
  -> FastAPI matches /wells/polygon
  -> FastAPI reads required points query parameter
  -> wells_in_polygon() receives points
  -> read database path from request.app.state.database_path
  -> read_cached_polygon_api_numbers(database_path, points)
      -> read database modified time
      -> check LRU cache
      -> on miss:
          -> parse_polygon_points(points)
              -> split by semicolon
              -> parse each lat,lon pair
              -> validate numeric/range/finite values
              -> require at least 3 distinct coordinates
              -> close polygon if needed
              -> build Shapely Polygon using lon,lat order
              -> reject invalid/self-intersecting/zero-area polygons
              -> calculate min/max lat/lon bounds
          -> open SQLite read-only
          -> iter_wells_in_bounds(...)
              -> select API, Latitude, Longitude
              -> exclude null coordinates
              -> filter by bounding box
              -> order by API
          -> close SQLite connection
          -> for each candidate:
              -> point_is_covered_by_polygon(...)
              -> include candidate if polygon covers the point
          -> sort matching API numbers
  -> if polygon validation fails:
      -> raise HTTPException(422, detail)
  -> return {"api_numbers": api_numbers, "count": len(api_numbers)}
  -> json_cache_response(...)
      -> apply ETag and Cache-Control
      -> return 304 or full JSON
```

## Error Status Summary

`200 OK`

Returned when the request is valid and the response body is sent.

`304 Not Modified`

Returned when the client sends `If-None-Match` and the current ETag matches.

`404 Not Found`

Returned by `/well/{api_number}` when the API number format is valid, but no row
exists in the database.

`422 Unprocessable Entity`

Returned when:

- API number format is invalid.
- Polygon points are missing.
- Polygon points are malformed.
- Polygon geometry is invalid.

`503 Service Unavailable`

Returned when the configured SQLite database cannot be read.

## Key Design Characteristics

- The API is read-only.
- Runtime API requests do not scrape external websites.
- API numbers are public-facing as hyphenated or digit-only, but stored
  digit-only.
- Data normalization happens before SQLite loading.
- The database is the source of truth for API responses.
- SQLite reads are opened in read-only mode.
- Single-well and polygon queries use process-level LRU caching.
- Cache invalidation uses the SQLite file modified time.
- HTTP responses use `Cache-Control` and ETag.
- Polygon search uses a fast SQLite bounding-box filter before exact Shapely
  geometry checks.
- Response shape for well records is based on the assignment columns.
- The repository can read both assignment-style and snake_case database column
  names.

## Files To Know

```text
app/main.py
  FastAPI app factory, database-path setup, validation error handler.

app/api/routes/health.py
  /health route.

app/api/routes/wells.py
  /well/{api_number} and /wells/polygon routes.

app/api/cache.py
  Cache-Control, ETag, and 304 response helper.

app/api/docs.py
  OpenAPI metadata, route descriptions, examples, documented responses.

app/schemas/wells.py
  Public API-number validation and normalization.

app/services/well_queries.py
  Runtime API query services and LRU caching.

app/repositories/sqlite.py
  Read-only SQLite connection helper and DatabaseUnavailable error.

app/repositories/wells.py
  SQL queries, upsert logic, schema compatibility helpers.

app/repositories/schema.py
  Assignment columns, SQLite table schema, lat/lon index.

app/utils/geo.py
  Polygon parsing, validation, bounds, and point-in-polygon checks.

app/utils/normalize.py
  Source-data normalization, type coercion, API normalization, field repair.

app/services/ingestion.py
  Scraping loop, retries, checkpoint/report/CSV output.

app/services/well_details/parser.py
  NM OCD Well Details HTML/snapshot parser.

app/services/well_details/clients.py
  Firecrawl scrape and browser-session clients.

app/services/well_details/urls.py
  Official Well Details URL builder and API hyphenation.

app/cli/commands.py
  CLI commands for scraping, sessions, and database loading.
```
