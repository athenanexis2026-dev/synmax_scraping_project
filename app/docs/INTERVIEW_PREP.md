# SynMax Interview Prep

Use these answers as practice notes for the follow-up interview. The goal is not
to memorize every word, but to be comfortable explaining the engineering choices
behind the project.

## 1. Can You Walk Me Through Your Architecture From CSV Input To API Response?

The project starts with the provided CSV of well API numbers. The ingestion CLI
reads those API numbers, validates them, and then uses a supervised scraping
workflow to collect data from the NM OCD WellDetails site. Each scraped record is
normalized into the exact fields required by the assignment, then written into
both a CSV artifact and the SQLite database.

After ingestion, the FastAPI app exposes the data through read-only endpoints.
The `/well/{api_number}` endpoint does a direct lookup by API number, while
`/wells/polygon` handles geospatial search. I separated the system into CLI,
scraping, normalization, repository, service, and API layers so each part has one
clear responsibility and can be tested independently.

## 2. Why Did You Choose FastAPI, And Why Not Flask?

I chose FastAPI because this project is API-first. FastAPI gives strong request
validation, type-driven development, automatic OpenAPI documentation, and clean
support for testing through `TestClient`. For this assignment, that was useful
because the interviewer can run the service and immediately inspect `/docs` to
understand the available endpoints and expected inputs.

I did not choose Flask because Flask is more minimal by default. It is a great
framework, but for validation, typed request contracts, response documentation,
and OpenAPI docs, I would have had to add more extensions or custom structure.
FastAPI gave me those pieces out of the box, which let me spend more time on the
scraping, data quality, database loading, and geospatial logic.

## 3. Why Did You Use SQLite, And What Would Change If This Became Production-Scale?

I used SQLite because the assignment explicitly asked for a SQLite database, and
for a 480-record take-home dataset it is a practical choice. It is easy to
inspect locally, easy to ship with the repository, and simple for the reviewer to
run without provisioning infrastructure.

In production, I would move to PostgreSQL, and specifically PostGIS for
geospatial queries. SQLite works well for the take-home, but Postgres would give
better concurrency, stronger operational tooling, better indexing options,
migrations, backups, and native geospatial functions. The API and service layers
are already separated enough that this migration would mostly affect the
repository/database layer.

## 4. How Did You Handle Scraping From The NM OCD WellDetails Site?

The current scraping flow uses Firecrawl browser sessions and browser snapshots.
That matters because the NM OCD site may not behave like a simple static page
fetch; it can require a real browser session and human verification before data
is visible.

The scraper opens or uses a verified browser session, navigates to the
WellDetails page for each API number, captures the browser snapshot, and then
extracts the relevant well data from that snapshot. I also built checkpointing
around the scrape so the process can resume safely if a session expires or the
site blocks progress.

## 5. What Problems Did You Run Into With Cloudflare Or Turnstile Protection?

The site can return Cloudflare or Turnstile verification instead of the actual
well data. I treated that as a real-world external dependency issue, not
something to hack around. The scraper detects protection content and records it
instead of pretending the scrape succeeded.

The responsible solution was a supervised browser workflow: a human can complete
the verification in the live browser session, and then the scraper continues from
that verified session. That keeps the project practical while respecting the
site's protection mechanisms.

## 6. How Does Your Scraper Recover If It Stops Halfway Through The 480 API Numbers?

The scraper writes progress into a checkpoint file after each API number.
Completed records, blocked records, and failed records are tracked separately.
That means a long scrape does not lose all progress if something goes wrong.

When the scraper runs again, it reads the checkpoint and skips API numbers that
were already completed. This makes the ingestion process resumable and
idempotent. Instead of starting over every time, it can continue from the last
known good state.

## 7. How Do You Validate And Normalize API Numbers?

I validate API numbers against the expected formats. The API can accept
hyphenated values like `30-015-25325` and digit-only values like `3001525325`.

Internally, I normalize API numbers to one canonical digit-only text format. That
avoids duplicate representations of the same well and keeps database lookups
consistent. I store them as text rather than integers because API numbers are
identifiers, not values for arithmetic, and text preserves formatting safely.

## 8. Why Did You Store API Numbers As Digit-Only Values In The Database?

I wanted one canonical representation in storage. If one row used
`30-015-25325` and another used `3001525325`, the database could treat the same
well as two different records. Normalizing to digit-only text prevents that.

At the API boundary, I can still be user-friendly and accept both formats. But
inside the database, consistency matters more than presentation.

## 9. How Did You Map The Scraped Data Into The Required `api_well_data` Columns?

I used a normalization layer between scraping and storage. The snapshot
extraction gives me source fields, and the normalizer maps those fields into the
exact assignment columns.

That was important because the assignment required specific column names like
`Well Type`, `Directional Status`, `Single/Multiple Completion`, `Spud Date`,
`TVD`, `Latitude`, and `Longitude`. I wanted the SQLite table to match the
requirements exactly while keeping the Python code organized.

## 10. How Did You Ensure The Database Schema Matched The Assignment While Still Keeping The Code Maintainable?

I made the SQLite table match the assignment directly, including the required
table name `api_well_data` and the exact column names. That reduces evaluator
risk because they can open the database and immediately see the required schema.

At the same time, I kept database access behind repository functions. The rest
of the application does not need to know every SQL detail. That keeps the project
maintainable even though the database column names include spaces and special
characters.

## 11. How Does The `/well/{api_number}` Endpoint Work Internally?

The endpoint first validates the API number format, then normalizes it to the
internal digit-only representation. After that, it queries SQLite by the `API`
primary key.

If the well exists, the endpoint returns all available fields from the database.
If the well does not exist, it returns a `404`. If the database is missing or
unavailable, it returns a `503`. I wanted the API behavior to be predictable and
easy to debug.

## 12. How Does The Polygon Endpoint Determine Whether A Well Is Inside The Polygon?

The polygon endpoint accepts latitude/longitude pairs from the user. It validates
that the points are numeric, within valid latitude/longitude ranges, and form a
real polygon.

Then it checks wells against that polygon. I used Shapely for the exact geometry
check, and specifically `covers()` so wells on the polygon boundary are
included. That is usually the more intuitive behavior for this kind of search.

## 13. Why Do You Use A SQL Bounding-Box Query Before The Exact Polygon Check?

The bounding-box query is a performance optimization. Before doing geometry
checks, SQLite filters wells to only those whose latitude and longitude fall
within the polygon's outer bounds.

For 480 wells, the endpoint would work even without this optimization. But the
bounding-box step shows how I would think about scale: reduce the candidate set
cheaply in the database, then apply the more precise geometry logic only to
likely matches.

## 14. What Tests Did You Write, And What Risks Do They Cover?

I wrote tests across the main risk areas: API behavior, geospatial validation,
ingestion, normalization, repository/database behavior, CLI behavior, and
scraping/parser logic.

The tests cover malformed API numbers, missing wells, invalid polygons, boundary
points, database loading, field normalization, and endpoint responses. The
current test suite passes with `51` tests, which gives confidence that the core
behavior works and regressions would be caught quickly.

## 15. If You Had Another Week, What Would You Improve Or Add?

If I had another week, I would focus on turning the take-home into something
easier to evaluate, deploy, and use.

First, I would deploy the API publicly so the reviewer could test it without
running the project locally. I would probably use a simple cloud deployment with
environment-based configuration and a documented production startup command.

Second, I would move from SQLite to PostgreSQL, and for the geospatial side I
would use PostGIS. That would let the database handle polygon search natively
with spatial indexes instead of doing the final geometry check in Python. It
would also make the system more realistic for production workloads.

Third, I would add Docker. I would create a Dockerfile and Docker Compose setup
so the API, database, and environment can be started consistently with one
command. That would remove local setup friction and make the project much easier
to review.

Finally, I would build a small front-end. The front-end would let users search
by API number, enter or draw a polygon, call the API, and view matching wells on
a map or in a table. That would make the project easier to demo and would show
the API as a usable data product, not just backend endpoints.
