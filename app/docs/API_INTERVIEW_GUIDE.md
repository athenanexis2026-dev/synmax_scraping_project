This API has three public endpoints:

```text
GET /health
GET /well/{api_number}
GET /wells/polygon?points=...
```

The best interview structure is:

```text
1. Start with app creation and shared state.
2. Visit the endpoint route function.
3. Follow validation and normalization.
4. Follow the service function.
5. Follow the repository/database read.
6. Explain service-level caching.
7. Explain HTTP ETag caching.
8. Mention the tests that prove the behavior.
```

## 1. Start Here: App Startup

Visit these functions first:

```text
app/main.py:52  create_app()
app/main.py:23  get_database_path()
app/main.py:36  readable_validation_exception_handler()
```

What to say:

```text
The API is created in create_app(). At startup, it reads SYNMAX_DATABASE_PATH,
stores the result on api.state.database_path, registers the routers, and
registers a custom validation handler for cleaner API-number errors.
```

Important details to point out:

```text
create_app()
  -> FastAPI(**APP_METADATA)
  -> api.state.database_path = get_database_path()
  -> add_exception_handler(RequestValidationError, readable_validation_exception_handler)
  -> include_router(health_router)
  -> include_router(wells_router)
```

Why it matters:

```text
Routes do not read environment variables directly. They read the configured
database path from request.app.state.database_path. That keeps configuration in
one startup location.
```

## 2. Endpoint: GET /health

Visit these functions in order:

```text
app/api/routes/health.py:16  health()
app/repositories/sqlite.py:19  connect_readonly()
```

Step-by-step code tour:

```text
1. health(request) receives the FastAPI request.
2. It reads request.app.state.database_path.
3. It calls connect_readonly(database_path).
4. It runs SELECT 1 FROM api_well_data LIMIT 1.
5. It closes the connection.
6. If the read succeeds, it returns {"status": "ok", "database": "connected"}.
7. If the database cannot be read, it raises HTTP 503.
```

What to say:

```text
/health is a readiness endpoint. It confirms the app is alive and that the
configured SQLite database can be opened in read-only mode. It does not return
well data and it does not use the ETag response helper because it is a health
check, not a cacheable data endpoint.
```

Tests to mention:

```text
tests/test_api.py:16  test_health_returns_database_status
tests/test_api.py:25  test_health_returns_503_for_missing_database
```

## 3. Endpoint: GET /well/{api_number}

Visit these functions in order:

```text
app/api/routes/wells.py:40       read_well()
app/schemas/wells.py:13         API_NUMBER_PATTERN_TEXT
app/schemas/wells.py:21         normalize_hyphenated_api_number()
app/services/well_queries.py:29 read_cached_well()
app/services/well_queries.py:17 database_mtime_ns()
app/services/well_queries.py:40 _cached_get_well()
app/repositories/sqlite.py:19   connect_readonly()
app/repositories/wells.py:101   get_well()
app/api/cache.py:22             json_cache_response()
```

Step-by-step code tour:

```text
1. FastAPI matches /well/{api_number}.
2. FastAPI validates api_number with API_NUMBER_PATTERN_TEXT.
3. read_well() runs normalize_hyphenated_api_number(api_number).
4. normalize_hyphenated_api_number() validates again and removes hyphens.
5. read_well() reads database_path from request.app.state.database_path.
6. read_well() calls read_cached_well(database_path, normalized_api).
7. read_cached_well() adds the database modified time to the cache key.
8. _cached_get_well() opens a read-only SQLite connection.
9. get_well() queries api_well_data by the normalized API number.
10. If no row exists, read_well() returns HTTP 404.
11. If a row exists, read_well() calls json_cache_response(well, request).
12. json_cache_response() returns either 200 with JSON or 304 Not Modified.
```

What to say about validation:

```text
There are two validation layers. FastAPI validates the path parameter before the
route runs, using API_NUMBER_PATTERN_TEXT. Then normalize_hyphenated_api_number()
does a defensive validation check and converts public formats like
30-015-25325 into the storage key 3001525325.
```

Accepted formats:

```text
30-015-25325       -> 3001525325
3001525325         -> 3001525325
30-015-45678-0000 -> 30015456780000
30015456780000    -> 30015456780000
```

What to say about the database read:

```text
The repository layer owns SQL. get_well() selects the expected assignment
columns from api_well_data and returns a plain dict. It also supports both the
original human-readable column names and snake_case aliases through helper
functions like _source_column().
```

Tests to mention:

```text
tests/test_api.py:33   test_get_well_returns_exact_columns_and_cache_headers
tests/test_api.py:75   test_get_well_accepts_digit_only_api_number
tests/test_api.py:85   test_get_well_rejects_malformed_api_number
tests/test_api.py:94   test_get_well_accepts_four_segment_hyphenated_api_number
tests/test_api.py:108  test_get_well_returns_404_for_missing_well
```

## 4. Caching For GET /well/{api_number}

There are two cache layers to explain.

### Service-Level LRU Cache

Visit these functions:

```text
app/services/well_queries.py:29 read_cached_well()
app/services/well_queries.py:17 database_mtime_ns()
app/services/well_queries.py:40 _cached_get_well()
```

What to say:

```text
read_cached_well() builds a cache key from the database path, the database file
modified time, and the normalized API number. _cached_get_well() is decorated
with @lru_cache(maxsize=512), so repeated requests for the same normalized well
can skip another SQLite read while the database file has not changed.
```

Cache key idea:

```text
database path + database mtime ns + normalized API number
```

Example:

```text
/well/30-015-25325 -> normalize to 3001525325 -> cache key uses 3001525325
/well/3001525325   -> normalize to 3001525325 -> same service cache entry
```

Why database mtime matters:

```text
If the SQLite file changes, database_mtime_ns() returns a new value. That makes
new requests use a new cache key, so stale results are not reused.
```

### HTTP ETag Cache

Visit these functions:

```text
app/api/cache.py:22 json_cache_response()
app/api/cache.py:32 build_etag()
app/api/cache.py:42 etag_matches()
```

What to say:

```text
After the server has the well content, json_cache_response() builds a stable
ETag from the JSON body. The response includes Cache-Control: public,
max-age=300 and an ETag. If the client sends If-None-Match with the same ETag,
the API returns 304 Not Modified instead of sending the full JSON body again.
```

Important distinction:

```text
The LRU cache helps the server avoid repeated database work.
The ETag cache helps the client avoid downloading unchanged response bodies.
```

## 5. Endpoint: GET /wells/polygon

Visit these functions in order:

```text
app/api/routes/wells.py:68       wells_in_polygon()
app/services/well_queries.py:56 read_cached_polygon_api_numbers()
app/services/well_queries.py:17 database_mtime_ns()
app/services/well_queries.py:67 _cached_polygon_api_numbers()
app/utils/geo.py:27             parse_polygon_points()
app/utils/geo.py:79             _parse_coordinate_pair()
app/repositories/sqlite.py:19   connect_readonly()
app/repositories/wells.py:123   iter_wells_in_bounds()
app/utils/geo.py:67             point_is_covered_by_polygon()
app/api/cache.py:22             json_cache_response()
```

Step-by-step code tour:

```text
1. FastAPI matches /wells/polygon.
2. FastAPI requires the query parameter points.
3. wells_in_polygon() reads database_path from request.app.state.database_path.
4. It calls read_cached_polygon_api_numbers(database_path, points).
5. read_cached_polygon_api_numbers() adds the database modified time to the
   service cache key.
6. _cached_polygon_api_numbers() parses and validates the raw points string.
7. parse_polygon_points() turns lat,lon pairs into a Shapely polygon.
8. The service opens a read-only SQLite connection.
9. iter_wells_in_bounds() finds candidate wells inside the polygon bounding box.
10. point_is_covered_by_polygon() does the exact Shapely polygon check.
11. The service sorts matching API numbers.
12. wells_in_polygon() builds {"api_numbers": api_numbers, "count": len(api_numbers)}.
13. json_cache_response() returns either 200 with JSON or 304 Not Modified.
```

What to say about the points format:

```text
The API accepts points as latitude,longitude pairs separated by semicolons:
32,-105;33,-105;33,-104;32,-104
```

What to say about coordinate conversion:

```text
The public API accepts latitude,longitude, but Shapely geometry uses x,y. For
geographic coordinates, x,y means longitude,latitude. parse_polygon_points()
performs that conversion when creating the polygon, and
point_is_covered_by_polygon() performs it again for each well point.
```

What to say about polygon matching:

```text
The polygon search is two-phase. First, iter_wells_in_bounds() uses SQL to find
wells inside the polygon's bounding rectangle. Then point_is_covered_by_polygon()
does the exact geometry check with polygon.covers(point). The code uses covers()
instead of contains() so wells on the polygon boundary are included.
```

Tests to mention:

```text
tests/test_api.py:116  test_wells_polygon_returns_sorted_api_numbers_and_cache_headers
tests/test_api.py:152  test_wells_polygon_requires_points_query_parameter
tests/test_api.py:160  test_wells_polygon_rejects_two_distinct_points
tests/test_api.py:168  test_wells_polygon_rejects_malformed_points
tests/test_geo.py:10   test_parse_polygon_points_closes_polygon_and_calculates_bounds
tests/test_geo.py:20   test_point_is_covered_by_polygon_includes_boundary
tests/test_geo.py:39   test_parse_polygon_points_rejects_self_intersection
```

## 6. Caching For GET /wells/polygon

There are also two cache layers for polygon search.

### Service-Level LRU Cache

Visit these functions:

```text
app/services/well_queries.py:56 read_cached_polygon_api_numbers()
app/services/well_queries.py:17 database_mtime_ns()
app/services/well_queries.py:67 _cached_polygon_api_numbers()
```

What to say:

```text
read_cached_polygon_api_numbers() builds a cache key from the database path,
the database file modified time, and the raw points string. The cached function
uses @lru_cache(maxsize=128), so identical polygon requests can skip parsing,
SQL candidate lookup, and exact Shapely filtering.
```

Cache key idea:

```text
database path + database mtime ns + raw points string
```

Important detail:

```text
The polygon cache uses the raw points string. Two strings that describe the same
shape but use different formatting are different service cache keys.
```

Example:

```text
32,-105;33,-105;33,-104;32,-104
32.0,-105.0;33.0,-105.0;33.0,-104.0;32.0,-104.0
```

Those are equivalent shapes, but different raw strings.

### HTTP ETag Cache

Visit the same HTTP cache helper used by `/well/{api_number}`:

```text
app/api/cache.py:22 json_cache_response()
app/api/cache.py:32 build_etag()
app/api/cache.py:42 etag_matches()
```

What to say:

```text
The polygon route returns a JSON object with api_numbers and count. That object
goes through json_cache_response(), which builds an ETag from the stable JSON
payload. If the client repeats the request with a matching If-None-Match header,
the API returns 304 Not Modified.
```

Why sorting matters:

```text
_cached_polygon_api_numbers() returns sorted API numbers. Stable ordering makes
the response deterministic, which also helps produce stable ETags.
```

## 7. Error Handling To Explain

Visit these functions and exception paths:

```text
app/main.py:36               readable_validation_exception_handler()
app/api/routes/wells.py:40   read_well()
app/api/routes/wells.py:68   wells_in_polygon()
app/utils/geo.py:11          PolygonValidationError
app/repositories/sqlite.py:12 DatabaseUnavailable
```

What to say:

```text
Malformed API numbers fail with 422. For path validation errors on api_number,
readable_validation_exception_handler() returns a cleaner message than the
default FastAPI validation response.

If a well API number is valid but not found, read_well() returns 404.

Malformed polygon input raises PolygonValidationError, and wells_in_polygon()
translates that into HTTP 422.

Database read failures raise DatabaseUnavailable, and the route functions
translate that into HTTP 503.
```

## 8. Short Interview Script

Use this if you need a concise spoken answer:

```text
The app starts in create_app(), reads SYNMAX_DATABASE_PATH once, stores it on
app.state, and registers the health and wells routers. /health opens the
database read-only and runs a tiny readiness query.

For /well/{api_number}, FastAPI first validates the path format. The route then
normalizes the API number to digits only, reads the database path from app
state, and calls read_cached_well(). That service function includes the
database mtime in the LRU cache key, so repeated requests are fast but database
updates naturally create new cache keys. On a cache miss, _cached_get_well()
opens SQLite read-only and get_well() performs the SQL lookup. The route returns
404 if there is no row, otherwise it passes the record to json_cache_response()
for Cache-Control and ETag handling.

For /wells/polygon, the route requires the points query string and calls
read_cached_polygon_api_numbers(). The service cache key uses database path,
database mtime, and the raw points string. On a cache miss, parse_polygon_points()
validates the lat,lon pairs, auto-closes the polygon, and creates a Shapely
polygon. Then iter_wells_in_bounds() gets SQL candidates inside the bounding
box, and point_is_covered_by_polygon() runs the exact geometry check with
covers(), which includes boundary points. The API sorts the API numbers, returns
api_numbers and count, and uses the same ETag helper as the single-well route.

So the service LRU caches help the server avoid repeated read and geometry work,
while the HTTP ETag cache helps clients avoid downloading unchanged JSON.
```

## 9. Common Interview Follow-Up Questions

### Why use both LRU caching and ETag caching?

```text
They solve different problems. LRU caching is internal and reduces server-side
work. ETag caching is HTTP-level and reduces client/network work.
```

### Why include database modified time in the LRU cache key?

```text
Because this is a read-only API over a SQLite data file. If the file changes,
the mtime changes, so new requests stop matching old cache entries.
```

### Why normalize API numbers before lookup?

```text
The public API supports human-friendly hyphenated formats and digit-only
formats. The database lookup uses one canonical digit-only key, so both public
formats resolve to the same stored well.
```

### Why use polygon.covers() instead of polygon.contains()?

```text
covers() includes points inside the polygon and points exactly on the boundary.
That is usually better for a search area because wells on the border should be
included instead of unexpectedly excluded.
```

### Why do a bounding-box query before the exact polygon check?

```text
The SQL bounding-box query cheaply removes wells that are obviously outside the
area. Shapely then runs the more precise geometry check only on candidates.
```
