# SynMax API Flow

This document explains the runtime API flow for this project. It focuses only
on how the public APIs behave: routes, validation, request normalization,
response caching, polygon search behavior, and why the API depends on
normalized/repaired data.

The API is a read-only FastAPI service. Runtime requests do not create or
modify well records. A request comes in, gets validated, may be normalized,
queries the configured data source through the service/repository layers, and
returns JSON with HTTP caching headers.

## Runtime API Overview

The public API surface has three main endpoints:

```text
GET /health
GET /well/{api_number}
GET /wells/polygon?points=...
```

At runtime, the flow is:

```text
HTTP request
  -> FastAPI route matching
  -> FastAPI/path/query validation
  -> route-specific normalization
  -> service-layer cache lookup
  -> service/repository read
  -> route-level error handling
  -> HTTP response cache handling
  -> JSON response or 304 Not Modified
```

The main API files are:

```text
app/main.py
app/api/routes/health.py
app/api/routes/wells.py
app/schemas/wells.py
app/utils/geo.py
app/services/well_queries.py
app/api/cache.py
```

## App Startup And Shared API State

Main file: `app/main.py`

The API application is created by:

```python
app = create_app()
```

`create_app()` does four API-specific things:

```text
1. Creates the FastAPI app using metadata from app/api/docs.py.
2. Reads SYNMAX_DATABASE_PATH.
3. Stores the path in api.state.database_path.
4. Registers routers and a custom validation error handler.
```

The important shared state is:

```python
api.state.database_path = get_database_path()
```

Every route uses this same configured path through:

```python
request.app.state.database_path
```

This is why the route functions do not read `.env` or environment variables.
Configuration happens once at app startup, then the routes use app state.

## Route: GET /health

Main file: `app/api/routes/health.py`

Purpose: confirm that the API is alive and the configured data source can be
read.

Flow:

```text
GET /health
  -> health(request)
  -> read database_path from request.app.state
  -> try to open a read-only connection
  -> run a minimal readiness query
  -> close the connection
  -> return {"status": "ok", "database": "connected"}
```

Success response:

```json
{
  "status": "ok",
  "database": "connected"
}
```

Possible error:

```text
503 Service Unavailable
```

This happens if the configured data source is unavailable. This endpoint does
not return well data and does not use the JSON ETag helper because it is a
readiness check, not a cacheable data response.

## Route: GET /well/{api_number}

Main file: `app/api/routes/wells.py`

Purpose: return a single well record by API number.

Example request:

```text
GET /well/30-015-25325
```

The route function is:

```python
read_well(request, api_number)
```

Detailed route flow:

```text
GET /well/30-015-25325
  -> FastAPI matches /well/{api_number}
  -> FastAPI validates api_number against API_NUMBER_PATTERN_TEXT
  -> read_well() receives api_number
  -> normalize_hyphenated_api_number(api_number)
      -> validates the format again
      -> removes hyphens
      -> returns digit-only API number
  -> route reads request.app.state.database_path
  -> route calls read_cached_well(database_path, normalized_api)
  -> service returns a well dict or None
  -> if None, route raises 404
  -> route passes well dict to json_cache_response()
  -> API returns JSON, or 304 if client's ETag is still current
```

Accepted API number formats:

```text
30-015-25325
3001525325
30-015-45678-0000
30015456780000
```

Normalization examples:

```text
30-015-25325       -> 3001525325
3001525325         -> 3001525325
30-015-45678-0000 -> 30015456780000
30015456780000    -> 30015456780000
```

Possible responses:

```text
200 OK
  Well exists and the API returns JSON.

304 Not Modified
  Client sent If-None-Match and the response ETag has not changed.

404 Not Found
  API number format is valid, but no well was found.

422 Unprocessable Entity
  API number format is invalid.

503 Service Unavailable
  Configured data source cannot be read.
```

## Where Validation Happens For GET /well/{api_number}

Validation happens in more than one place.

### 1. FastAPI Path Validation

Main file: `app/api/routes/wells.py`

The route parameter is declared with:

```python
api_number: str = ApiPath(
    pattern=API_NUMBER_PATTERN_TEXT,
    description=API_NUMBER_DESCRIPTION,
    examples=API_NUMBER_EXAMPLES,
)
```

That means FastAPI checks the path value before the route function is allowed
to run normally.

If this request comes in:

```text
GET /well/30015
```

FastAPI sees that `30015` does not match the pattern.

### 2. Custom Validation Error Formatting

Main file: `app/main.py`

FastAPI produces a `RequestValidationError`. The app registers:

```python
readable_validation_exception_handler()
```

That handler checks whether the validation error came from:

```text
("path", "api_number")
```

If yes, it returns this cleaner response:

```json
{
  "detail": "api_number must use one of these formats: 30-015-25325, 3001525325, 30-015-45678-0000, or 30015456780000"
}
```

This is easier for API users than FastAPI's default detailed validation object.

### 3. Explicit Normalization Validation

Main file: `app/schemas/wells.py`

The function:

```python
normalize_hyphenated_api_number(api_number)
```

also validates the value:

```python
if not API_NUMBER_PATTERN.fullmatch(api_number):
    raise HTTPException(status_code=422, detail=API_NUMBER_ERROR)
```

This is a defensive second check. If the function is ever called from somewhere
else, it still refuses malformed API numbers.

## API Number Validation Rule

Main file: `app/schemas/wells.py`

The pattern is:

```python
API_NUMBER_PATTERN_TEXT = r"^(?:\d{10}(?:\d{4})?|\d{2}-\d{3}-\d{5}(?:-\d{4})?)$"
```

It accepts exactly two families of API numbers:

```text
10 digit:
  3001525325
  30-015-25325

14 digit:
  30015456780000
  30-015-45678-0000
```

It does not try to guess or fix malformed input. For example:

```text
30015                 invalid
30-15-25325           invalid
30-015-25325-extra    invalid
abc                   invalid
```

The API behaves this way because API numbers are identifiers. If the identifier
is malformed, guessing could return the wrong well.

## Caching For GET /well/{api_number}

The single-well endpoint uses two cache layers:

1. Service-level LRU cache.
2. HTTP ETag cache.

They happen at different times and solve different problems.

### Service-Level Cache For GET /well

Main file: `app/services/well_queries.py`

The route calls:

```python
read_cached_well(database_path, normalized_api)
```

That function calls:

```python
_cached_get_well(str(database_path), database_mtime_ns, normalized_api)
```

The cached function is:

```python
@lru_cache(maxsize=512)
def _cached_get_well(database_path, database_mtime_ns, normalized_api):
```

The cache key is effectively:

```text
database path + database modified time + normalized API number
```

Example:

```text
database path: /path/to/api_well_data.db
database mtime: 1780000000000000000
normalized API: 3001525325
```

If another request asks for the same API number and the database file has not
changed, Python can return the cached result without opening and querying the
data source again.

Request 1:

```text
GET /well/30-015-25325
  -> normalized to 3001525325
  -> cache miss
  -> read data
  -> store result in LRU cache
```

Request 2:

```text
GET /well/3001525325
  -> normalized to 3001525325
  -> same normalized key
  -> same database modified time
  -> cache hit
  -> no repeated read needed
```

This works even though the user used two different public formats, because both
requests normalize to the same digit-only API number.

### Why Database Modified Time Is In The Cache Key

The service reads:

```python
database_path.stat().st_mtime_ns
```

That value is included in the LRU cache key. If the configured data file is
updated, the modified time changes.

Before update:

```text
key = db path + old mtime + 3001525325
```

After update:

```text
key = db path + new mtime + 3001525325
```

Because the key changed, the old cached result is not reused.

Important detail: the code does not manually clear the old LRU cache. Old
entries remain in memory until evicted by the LRU policy, but they stop matching
new requests once the modified time changes.

### HTTP ETag Cache For GET /well

Main file: `app/api/cache.py`

After the route has the well result, it calls:

```python
json_cache_response(well, request)
```

This builds an ETag from the response content:

```text
serialize JSON with sorted keys
  -> SHA-256 hash
  -> quote the hash
```

The response includes:

```text
Cache-Control: public, max-age=300
ETag: "<sha256-of-response-json>"
```

First request:

```text
GET /well/30-015-25325
  -> API returns 200 OK
  -> response includes full JSON body
  -> response includes ETag
```

Second request from a client that saved the ETag:

```text
GET /well/30-015-25325
If-None-Match: "<same-etag>"
```

If the well JSON has not changed:

```text
API returns 304 Not Modified
```

A `304` response has no full JSON body. It tells the client: "Use the copy you
already have."

### How Both GET /well Caches Work Together

For `/well/{api_number}`, the caching order is:

```text
request comes in
  -> normalize API number
  -> service-level LRU cache may avoid repeated data read
  -> route gets content
  -> HTTP ETag may avoid sending the full JSON body
```

The service cache helps the server.

The ETag cache helps the client.

## Route: GET /wells/polygon

Main file: `app/api/routes/wells.py`

Purpose: find wells whose latitude/longitude points are inside a polygon or on
its boundary.

Example request:

```text
GET /wells/polygon?points=32,-105;33,-105;33,-104;32,-104
```

Expected `points` format:

```text
lat,lon;lat,lon;lat,lon
```

Example response:

```json
{
  "api_numbers": ["3001525325", "3001525326"],
  "count": 2
}
```

Detailed route flow:

```text
GET /wells/polygon?points=32,-105;33,-105;33,-104;32,-104
  -> FastAPI matches /wells/polygon
  -> FastAPI reads required query parameter points
  -> wells_in_polygon() receives raw points string
  -> route reads request.app.state.database_path
  -> route calls read_cached_polygon_api_numbers(database_path, points)
  -> service validates and parses the polygon on cache miss
  -> service finds candidate wells using polygon bounds
  -> service filters candidates using exact polygon coverage
  -> service returns sorted API numbers
  -> route returns {"api_numbers": api_numbers, "count": len(api_numbers)}
  -> route passes response through json_cache_response()
```

Possible responses:

```text
200 OK
  Polygon is valid and the API returns matching API numbers.

304 Not Modified
  Client sent If-None-Match and the response ETag has not changed.

422 Unprocessable Entity
  points is missing, malformed, out of range, or not a valid polygon.

503 Service Unavailable
  Configured data source cannot be read.
```

## Where Validation Happens For GET /wells/polygon

Validation happens in two places.

### 1. FastAPI Query Parameter Validation

Main file: `app/api/routes/wells.py`

The route declares:

```python
points: str = ApiQuery(
    description=POLYGON_POINTS_DESCRIPTION,
    examples=POLYGON_POINTS_EXAMPLES,
)
```

Because `points` has no default value, FastAPI treats it as required.

This request is invalid:

```text
GET /wells/polygon
```

FastAPI returns `422` before the route can perform polygon parsing.

### 2. Polygon Content Validation

Main file: `app/utils/geo.py`

The service eventually calls:

```python
parse_polygon_points(points)
```

That function validates the actual content of the string.

Rules:

```text
points cannot be empty
points cannot contain empty coordinate pairs
each coordinate pair must be lat,lon
latitude and longitude must be numeric
latitude and longitude must be finite
latitude must be between -90 and 90
longitude must be between -180 and 180
at least three distinct coordinate pairs are required
polygon is automatically closed if needed
polygon cannot be empty
polygon must be geometrically valid
polygon cannot have zero area
polygon cannot be self-intersecting
```

Invalid examples:

```text
points=
32,-105;
32,-105;33,-105
32,-105;nope;33,-104
91,-105;33,-105;33,-104
0,0;1,1;1,0;0,1
```

The last example is invalid because it creates a self-intersecting polygon.

## Polygon Coordinate Handling

The API accepts coordinate pairs in this order:

```text
latitude,longitude
```

Example:

```text
32,-105
```

Internally, Shapely expects geometry coordinates in `x,y` order. For geographic
data, that means:

```text
longitude,latitude
```

So the API input:

```text
32,-105
```

is converted into this geometry point:

```text
(-105, 32)
```

This conversion happens when creating the polygon and when checking each well
point.

## Polygon Auto-Closing

A polygon should start and end at the same coordinate. The API does not require
the user to repeat the first coordinate manually.

If the user sends:

```text
32,-105;33,-105;33,-104;32,-104
```

the parser treats it as:

```text
32,-105;33,-105;33,-104;32,-104;32,-105
```

This makes the API easier to use while still creating a valid closed polygon.

## Polygon Boundary Behavior

The API includes wells on the polygon boundary.

This happens because the code uses:

```python
polygon.covers(point)
```

Instead of:

```python
polygon.contains(point)
```

The practical difference:

```text
contains()
  -> true only for points strictly inside the polygon

covers()
  -> true for points inside or exactly on the boundary
```

For this API, boundary inclusion is useful because a well exactly on the border
of a search area should not disappear unexpectedly.

## Polygon Search Logic

The polygon endpoint does not immediately run an exact polygon check against
every well.

The service uses a two-step search:

```text
1. Bounding-box candidate search.
2. Exact Shapely polygon check.
```

### Step 1: Bounding-Box Candidate Search

After parsing the polygon, the service knows:

```text
min_latitude
max_latitude
min_longitude
max_longitude
```

It uses those bounds to find only wells whose coordinates are inside the
rectangle around the polygon.

Example:

```text
polygon bounds:
  latitude:  32 to 33
  longitude: -105 to -104
```

Candidate wells must satisfy:

```text
Latitude BETWEEN 32 AND 33
Longitude BETWEEN -105 AND -104
```

This removes wells that are obviously outside the polygon area.

### Step 2: Exact Polygon Check

The bounding box is only a rectangle. A polygon can be triangular, irregular,
or concave. Some points can be inside the bounding rectangle but outside the
actual polygon.

So each candidate is checked with:

```python
point_is_covered_by_polygon(
    parsed_polygon.polygon,
    candidate["Latitude"],
    candidate["Longitude"],
)
```

Only candidates covered by the actual polygon are returned.

### Sorting

The endpoint returns sorted API numbers:

```python
return sorted(matching_api_numbers)
```

That gives clients a stable response order. Stable ordering is also important
for ETag caching because the same set of results should produce the same JSON
and the same ETag.

## Caching For GET /wells/polygon

The polygon endpoint also uses two cache layers:

1. Service-level LRU cache.
2. HTTP ETag cache.

### Service-Level Cache For Polygon

Main file: `app/services/well_queries.py`

The route calls:

```python
read_cached_polygon_api_numbers(database_path, points)
```

That function calls:

```python
_cached_polygon_api_numbers(str(database_path), database_mtime_ns, points)
```

The cached function is:

```python
@lru_cache(maxsize=128)
def _cached_polygon_api_numbers(database_path, database_mtime_ns, points):
```

The cache key is effectively:

```text
database path + database modified time + raw points string
```

Example:

```text
database path: /path/to/api_well_data.db
database mtime: 1780000000000000000
points: 32,-105;33,-105;33,-104;32,-104
```

First polygon request:

```text
GET /wells/polygon?points=32,-105;33,-105;33,-104;32,-104
  -> cache miss
  -> parse polygon
  -> find bounding-box candidates
  -> run Shapely checks
  -> sort API numbers
  -> store result in LRU cache
```

Second identical polygon request:

```text
GET /wells/polygon?points=32,-105;33,-105;33,-104;32,-104
  -> same raw points string
  -> same database modified time
  -> cache hit
  -> skip polygon parsing and search work
```

Important detail: the polygon cache uses the raw `points` string.

These two requests describe the same polygon shape:

```text
32,-105;33,-105;33,-104;32,-104
32.0,-105.0;33.0,-105.0;33.0,-104.0;32.0,-104.0
```

But they are different raw strings, so they are different cache keys. The API
does not canonicalize polygon strings before caching.

### Why Polygon Cache Size Is Smaller

The polygon cache size is:

```text
128 entries
```

The single-well cache size is:

```text
512 entries
```

Polygon responses can be more expensive to compute and may vary more widely
because users can submit many different shapes. A smaller cache prevents the
process from keeping too many unique polygon result sets in memory.

### HTTP ETag Cache For Polygon

After the polygon route builds this response:

```json
{
  "api_numbers": ["3001525325", "3001525326"],
  "count": 2
}
```

it passes the response through:

```python
json_cache_response(content, request)
```

The API returns:

```text
Cache-Control: public, max-age=300
ETag: "<sha256-of-response-json>"
```

If a client repeats the same request with:

```text
If-None-Match: "<same-etag>"
```

and the response content is still the same, the API returns:

```text
304 Not Modified
```

This is useful for map UIs. A frontend may repeatedly ask for wells in the
same polygon while a user pans, refreshes, or returns to a previous search area.

### How Both Polygon Caches Work Together

For `/wells/polygon`, the caching order is:

```text
request comes in
  -> route receives raw points string
  -> service-level LRU cache may avoid repeated polygon/search work
  -> route builds response object
  -> HTTP ETag may avoid sending the full JSON body
```

Again:

```text
Service LRU cache helps the API server.
HTTP ETag cache helps the API client.
```

## HTTP Cache Helper

Main file: `app/api/cache.py`

Both `/well/{api_number}` and `/wells/polygon` use:

```python
json_cache_response(content, request)
```

This helper does the same thing for both endpoints:

```text
1. Build an ETag from the JSON content.
2. Add Cache-Control and ETag headers.
3. Check the request's If-None-Match header.
4. If the ETag matches, return 304.
5. Otherwise, return the full JSON response.
```

The cache-control header is:

```text
Cache-Control: public, max-age=300
```

The ETag is stable because the JSON is serialized with:

```text
sort_keys=True
compact separators
default=str
```

Stable JSON serialization matters because the same content should generate the
same hash.

## Why API Data Needs To Be Normalized And Repaired

Main file: `app/utils/normalize.py`

The runtime API depends on clean, predictable records. Without normalized and
repaired data, API responses would be inconsistent, hard to validate, and
harder for clients to consume.

The API response for `/well/{api_number}` is expected to have a stable shape:

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

However, source data can be inconsistent:

```text
One source may say "Current Operator"; the API should return "Operator".
One source may say "Type"; the API should return "Well Type".
One source may say "Direction"; the API should return "Directional Status".
Numeric fields may arrive as strings like "10,250" or "3210.0".
Empty strings should become null-like values, not empty text.
Latitude and longitude must be numeric for polygon search.
Dates can be embedded inside longer text.
Some fields can accidentally include neighboring labels or values.
```

Repair is needed because the API should not expose these source irregularities
directly to clients.

## API-Specific Reasons For Repair

### 1. Stable Response Shape

Clients should not have to guess whether the operator field is called:

```text
Operator
Current Operator
operator
```

The API returns one consistent field:

```text
Operator
```

This makes the API easier to consume from frontend code, scripts, dashboards,
or tests.

### 2. Correct Types

The API should return numeric values as numbers when possible.

Examples:

```text
"10,250" -> 10250
"32.75"  -> 32.75
""       -> None
```

This matters especially for:

```text
Latitude
Longitude
GL Elevation
KB Elevation
DF Elevation
TVD
```

The polygon endpoint depends on `Latitude` and `Longitude` being usable numeric
values.

### 3. Reliable API Number Lookup

The `/well/{api_number}` route normalizes the user's API number to digit-only.

For lookup to work, stored API values also need to be digit-only.

Example:

```text
request path: /well/30-015-25325
normalized request key: 3001525325
stored API must also be: 3001525325
```

If stored records used mixed formats, the same well could be missed.

### 4. Cleaner Yes/No Fields

Some fields, such as `Potash Waiver`, are expected to be simple values like:

```text
Yes
No
```

But source text can include long neighboring content. Repair extracts the
useful yes/no value when possible and avoids storing unrelated label text.

### 5. Safer Date Fields

Date fields can accidentally include dates from nearby labels. For example,
`Last Inspection` might contain text that includes another date from a different
field.

Repair avoids turning an unrelated neighboring date into the official
`Last Inspection` value.

### 6. Better Polygon Behavior

The polygon API can only include wells that have valid numeric coordinates.

If latitude or longitude is not repaired/coerced properly, the well cannot be
reliably checked against a polygon.

Clean coordinates make this flow possible:

```text
Latitude/Longitude from data
  -> numeric point
  -> Shapely polygon check
  -> include or exclude API number
```

## Runtime Normalization Versus Data Repair

There are two normalization moments relevant to the API:

```text
Request normalization:
  Happens during /well/{api_number}.
  Converts public API number input to digit-only lookup key.

Data repair/normalization:
  Happens before data is served by the API.
  Makes well records consistent, typed, and safe for API clients.
```

The runtime API does not repair full well records on every request. It expects
the records it reads to already be normalized. This keeps each API request fast
and predictable.

## Complete Flow: GET /well/{api_number}

```text
Client:
  GET /well/30-015-25325

FastAPI:
  Match /well/{api_number}
  Validate api_number path pattern

Route:
  normalize_hyphenated_api_number("30-015-25325")
  -> "3001525325"

Service cache:
  Build cache key:
    database path + database modified time + "3001525325"
  If key exists:
    return cached well result
  Else:
    read well result and store it in cache

Route:
  If no result:
    return 404
  Else:
    build response content

HTTP cache:
  Build ETag from well JSON
  If request If-None-Match matches:
    return 304
  Else:
    return 200 with JSON, Cache-Control, and ETag
```

## Complete Flow: GET /wells/polygon

```text
Client:
  GET /wells/polygon?points=32,-105;33,-105;33,-104;32,-104

FastAPI:
  Match /wells/polygon
  Ensure required points query parameter exists

Route:
  Pass raw points string to service

Service cache:
  Build cache key:
    database path + database modified time + raw points string
  If key exists:
    return cached API number list
  Else:
    continue

Polygon validation:
  Split points by semicolon
  Parse each lat,lon pair
  Validate numeric/range/finite values
  Require at least three distinct coordinates
  Auto-close polygon if needed
  Reject invalid geometry

Polygon search:
  Calculate min/max lat/lon bounds
  Find coordinate candidates inside bounds
  Convert each candidate to a Shapely point
  Include candidate if polygon.covers(point)
  Sort matching API numbers

Route:
  Build {"api_numbers": [...], "count": N}

HTTP cache:
  Build ETag from response JSON
  If request If-None-Match matches:
    return 304
  Else:
    return 200 with JSON, Cache-Control, and ETag
```

## API Error Summary

```text
200 OK
  Valid request, response body returned.

304 Not Modified
  Client cache is current, response body does not need to be sent again.

404 Not Found
  /well/{api_number} received a valid API number, but no matching well exists.

422 Unprocessable Entity
  Path or query input is malformed or invalid.

503 Service Unavailable
  Configured data source cannot be read.
```

## Key API Characteristics

- The API is read-only.
- Runtime API requests do not create, scrape, or repair well records.
- `/well/{api_number}` accepts hyphenated and digit-only API numbers.
- API-number input is validated before lookup.
- API-number input is normalized to digit-only before lookup.
- `/wells/polygon` requires a `points` query parameter.
- Polygon input uses `latitude,longitude` pairs separated by semicolons.
- Polygon validation happens before exact geospatial matching.
- Polygon boundary points are included.
- Single-well and polygon endpoints both use service-level LRU caching.
- Single-well and polygon endpoints both use HTTP ETag caching.
- Service-level cache invalidation depends on the configured data file modified
  time.
- HTTP caching uses `Cache-Control: public, max-age=300`.
- API responses depend on normalized/repaired source records so clients receive
  stable field names, cleaner values, and useful numeric types.
