# SynMax Python Take-Home Architecture Plan

Page 1

SynMax Python Take-Home Architecture

and 5-Day Build Plan

Prepared for Athena Nexis

Date: June 8, 2026

# Executive Summary

The take-home asks for a Python data project that scrapes New Mexico oil and gas well data, loads the results into a

SQLite table named api\_well\_data, and exposes an API for single-well lookup and polygon-based geospatial

search.

The best project is not just a scraper. It should look like a small production data service:

A repeatable ingestion command that reads the provided CSV, validates API numbers, fetches well records, parses

fields, and upserts into SQLite.

A clean SQL schema that satisfies the exact required table and column names while still letting the Python code use

readable snake\_case names.

A FastAPI service with typed request/response models, validation, useful error handling, and auto-generated

OpenAPI docs.

A geospatial search path that uses SQL bounding-box filtering first and then a tested point-in-polygon function in

Python.

A clear README, tests, and a generated CSV of polygon results for the required polygon.

This plan prioritizes correctness, explainability, and architectural maturity over unnecessary complexity. It also accounts

for the current reality that the NM OCD WellDetails page has changed since the assignment was written and may

present a Cloudflare Turnstile human-verification gate to automated requests.

# Requirements Parsed From The Take-Home

Part One requires:

Read apis\_pythondev\_test.csv, which contains several hundred well API numbers.

Fetch oil and gas well data from the NM OCD website.

Load all results into a SQLite database.

Create a single SQLite table called api\_well\_data.

Include these required columns:

SynMax Python Take-Home Architecture Plan

Page 2

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

Part Two requires:

A well endpoint that returns all available database fields for one API number.

A polygon search endpoint that accepts latitude/longitude pairs and returns API numbers located inside the polygon.

The final public Git repository must contain:

Web scraping and database loading code.

API code.

Local setup and run instructions.

The populated sqlite.db file.

A CSV containing API numbers returned by the polygon endpoint for:

\[(32.81,-104.19),(32.66,-104.32),(32.54,-104.24),(32.50,-104.03),(32.73,-104.01),(32.79,-103\
\
.91),(32.84,-104.05),(32.81,-104.19)\]

Evaluation focuses on:

SynMax Python Take-Home Architecture Plan

Page 3

Correct scraping and database loading.

Functioning API.

Creativity.

Quality of Python structure.

In-code documentation and readability.

# Input Data Observations

The provided apis\_pythondev\_test.csv contains:

480 API numbers.

480 valid values matching the NN-NNN-NNNNN format.

0 duplicates.

478 records with county code 015.

2 records with county code 005.

This is a good size for a take-home: small enough to run locally, but large enough to demonstrate batching, validation,

idempotent database writes, and meaningful API search.

# Current Upstream Website Reality

The assignment was written against the NM OCD WellDetails.aspx page. As of June 8, 2026, the public site has

recently changed. Search results and the site notice state that the WellDetails.aspx layout was updated on June 4,

2026 and that automated processes should transition to EMNRD API endpoints.

In addition, a direct programmatic request to the sample WellDetails URL can return a Cloudflare Turnstile

human-verification page instead of well data.

Recommended handling:

Do not attempt to bypass human-verification controls.

Build the data acquisition layer as a replaceable source adapter.

Implement the required scraping parser for assignment compliance.

If WellDetails is blocked during the build, use one of these responsible fallbacks:

Ask SynMax whether the official EMNRD API is acceptable given the current public notice.

Ask for a fixture/export if the reviewer expects the old page.

Use a public non-gated OCD results page only if it exposes the required fields reliably.

Keep the rest of the project independent from the upstream source.

This is a strong architecture story. It shows that the system can survive an external website layout change without

rewriting the API, SQL model, tests, or geospatial logic.

SynMax Python Take-Home Architecture Plan

Page 4

# Recommended Architecture

High-level flow:

apis\_pythondev\_test.csv

\|

v

CLI ingestion command

\|

v

WellSource adapter

WellDetails scraper

optional EMNRD API source

optional fixture source for tests

\|

v

HTML/JSON parser and normalizer

\|

v

Pydantic validation model

\|

v

Repository upsert layer

\|

v

SQLite api\_well\_data table

\|

+--------------------+

\|

v

FastAPI service

/well/{api}

/wells/search/polygon

/health

The key idea is separation of concerns:

The scraper knows how to talk to the external source.

The parser knows how to convert messy source data into a clean internal record.

The database layer knows how to store records safely.

The API layer knows how to serve data to customers.

The geometry layer knows how to answer the polygon question.

This structure is easy to test and easy to explain in an interview.

# Proposed Repository Structure

SynMax Python Take-Home Architecture Plan

Page 5

synmax-python-takehome/

README.md

pyproject.toml

Makefile

.env.example

app/

\_\_init\_\_.py

main.py # FastAPI app and route registration

config.py # Settings: DB path, timeouts, source URLs

db.py # SQLite engine/session helpers

schemas.py # Pydantic API request/response models

models.py # SQLAlchemy table mapping

scraper/

\_\_init\_\_.py

client.py # HTTP client, retries, timeout, source detection

parser.py # BeautifulSoup field extraction and normalization

load.py # CSV read, fetch, parse, validate, upsert workflow

sources.py # Source adapter protocol/classes

services/

\_\_init\_\_.py

well\_repository.py # Read/upsert database operations

geometry.py # Polygon parser and point-in-polygon logic

cli.py # Typer CLI: init-db, ingest, polygon-csv

data/

apis\_pythondev\_test.csv

sqlite.db

outputs/

polygon\_results.csv

tests/

test\_api.py

test\_csv\_validation.py

test\_geometry.py

test\_parser.py

fixtures/

well\_details\_sample.html

well\_details\_turnstile.html

Why this structure works:

It is small enough for a take-home.

It avoids a single giant script.

Each file has a clear reason to exist.

Tests can target individual units without hitting the live website.

The same repository can later evolve toward Postgres, Cloud Run, or scheduled ingestion.

# Main Technology Choices

Recommended dependencies:

SynMax Python Take-Home Architecture Plan

Page 6

fastapi

uvicorn\[standard\]

pydantic

sqlalchemy

httpx

beautifulsoup4

lxml

typer

python-dotenv

pytest

pytest-httpx

ruff

Optional only if time allows:

rich # nicer CLI output

shapely # robust geometry, but not necessary for this take-home

# SQL Architecture

Use SQLite because the assignment requires it. Design the schema as if it were a small production read model.

Important decision:

The SQLite table should use the exact required column names to reduce evaluator risk.

The Python code should still use Pythonic names through SQLAlchemy column keys.

For example, SQLAlchemy can map this:

Column("Well Type", String, key="well\_type")

That lets the actual SQLite column be "Well Type" while the Python code uses record.well\_type.

Recommended DDL:

SynMax Python Take-Home Architecture Plan

Page 7

CREATE TABLE IF NOT EXISTS api\_well\_data (

"Operator" TEXT,

"Status" TEXT,

"Well Type" TEXT,

"Work Type" TEXT,

"Directional Status" TEXT,

"Multi-Lateral" TEXT,

"Mineral Owner" TEXT,

"Surface Owner" TEXT,

"Surface Location" TEXT,

"GL Elevation" INTEGER,

"KB Elevation" INTEGER,

"DF Elevation" INTEGER,

"Single/Multiple Completion" TEXT,

"Potash Waiver" TEXT,

"Spud Date" TEXT,

"Last Inspection" TEXT,

"TVD" INTEGER,

"API" TEXT PRIMARY KEY NOT NULL,

"Latitude" REAL,

"Longitude" REAL,

"CRS" TEXT,

CHECK (

length("API") = 12

AND substr("API", 3, 1) = '-'

AND substr("API", 7, 1) = '-'

),

CHECK ("Latitude" IS NULL OR ("Latitude" BETWEEN -90 AND 90)),

CHECK ("Longitude" IS NULL OR ("Longitude" BETWEEN -180 AND 180))

);

CREATE INDEX IF NOT EXISTS idx\_api\_well\_data\_lat\_lon

ON api\_well\_data ("Latitude", "Longitude");

CREATE INDEX IF NOT EXISTS idx\_api\_well\_data\_status

ON api\_well\_data ("Status");

Why API is the primary key:

API numbers are unique well identifiers.

It prevents duplicates.

It makes re-running the scraper safe.

Why ISO text dates:

SQLite does not have a real native date type.

ISO strings like 2026-06-08 sort correctly.

The API can return null when a date is missing or unparseable.

Why an index on latitude and longitude:

The polygon endpoint should not scan all rows if the dataset grows.

First query by bounding box in SQL.

Then perform exact polygon inclusion in Python.

Optional production-style audit table:

SynMax Python Take-Home Architecture Plan

Page 8

CREATE TABLE IF NOT EXISTS scrape\_run\_log (

id INTEGER PRIMARY KEY AUTOINCREMENT,

started\_at TEXT NOT NULL,

finished\_at TEXT,

source\_name TEXT NOT NULL,

input\_count INTEGER NOT NULL,

success\_count INTEGER DEFAULT 0,

failure\_count INTEGER DEFAULT 0

);

Do not add audit fields to api\_well\_data unless you confirm the evaluator will tolerate extra columns. Keep the

required table clean.

# Python Data Model

Use one canonical internal model, then map it to SQL and API responses.

Plain-English idea:

The scraper gives us messy text.

The parser converts messy text into a dictionary.

Pydantic validates that dictionary and converts types.

The repository writes it to SQLite.

The API returns it as JSON.

Recommended Pydantic model:

class WellRecord(BaseModel):

api: str

operator: str \| None = None

status: str \| None = None

well\_type: str \| None = None

work\_type: str \| None = None

directional\_status: str \| None = None

multi\_lateral: str \| None = None

mineral\_owner: str \| None = None

surface\_owner: str \| None = None

surface\_location: str \| None = None

gl\_elevation: int \| None = None

kb\_elevation: int \| None = None

df\_elevation: int \| None = None

single\_multiple\_completion: str \| None = None

potash\_waiver: str \| None = None

spud\_date: date \| None = None

last\_inspection: date \| None = None

tvd: int \| None = None

latitude: float \| None = None

longitude: float \| None = None

crs: str \| None = None

Validation rules to include:

API number must match ^\\d{2}-\\d{3}-\\d{5}$.

Latitude must be between -90 and 90.

Longitude must be between -180 and 180.

SynMax Python Take-Home Architecture Plan

Page 9

Elevation and TVD fields should parse commas and empty strings safely.

Missing source values become None, not empty strings.

# Scraping And Loading Design

The ingestion command should be idempotent. Running it twice should not create duplicate rows or corrupt data.

Recommended command:

python -m app.cli ingest \

-csv data/apis\_pythondev\_test.csv \

-db data/sqlite.db \

-source well-details

Implementation steps:

1.

Read the CSV with utf-8-sig encoding to handle the BOM found in the sample file.

2.

Validate the api column exists.

3.

Validate every API value.

4.

Deduplicate before fetching.

5.

Fetch each well page with httpx.

6.

Use conservative concurrency, such as 3 to 5 requests at a time.

7.

Use timeouts and retry with exponential backoff.

8.

Detect blocked pages, especially pages containing cf-turnstile or Verifying you.

9.

Parse field labels into canonical fields.

10\. Validate with Pydantic.

11\. Upsert with INSERT ... ON CONFLICT("API") DO UPDATE.

12\. Print a final summary: input count, success count, failed count, output DB path.

Recommended source abstraction:

class WellSource(Protocol):

name: str

async def fetch(self, api\_number: str) -&gt; SourceDocument:

...

Concrete source options:

WellDetailsHtmlSource: assignment-compliant scraper.

EmnrdApiSource: optional official API adapter if SynMax approves it.

FixtureSource: used by tests so the tests do not rely on live network calls.

This is a senior-level design decision because the upstream source is the least stable part of the system.

SynMax Python Take-Home Architecture Plan

Page 10

# Parser Strategy

Do not depend only on brittle ASP.NET element IDs. They can change.

Better parser approach:

Parse the page with BeautifulSoup.

Build a normalized label/value map from visible text.

Normalize labels by lowercasing, trimming whitespace, removing punctuation, and collapsing spaces.

Use a dictionary of known label aliases.

Treat missing fields as None.

Save one or two HTML fixtures in tests/fixtures/ so the parser can be tested without the live site.

Example alias mapping:

FIELD\_ALIASES = {

"operator": "operator",

"current operator": "operator",

"status": "status",

"type": "well\_type",

"well type": "well\_type",

"work type": "work\_type",

"vertical depth": "tvd",

"tvd": "tvd",

"ground level": "gl\_elevation",

"gl elevation": "gl\_elevation",

"kelly bushing": "kb\_elevation",

"kb elevation": "kb\_elevation",

"drilling floor": "df\_elevation",

"df elevation": "df\_elevation",

"projection": "crs",

"crs": "crs",

}

Why this is better:

It survives small label changes.

It is explainable.

It is testable with fixtures.

# API Design

Use FastAPI. It fits the role and the assignment because it is Python, API-first, typed, and automatically documents the

API.

Recommended endpoints:

GET /health

GET /well/{api\_number}

GET /wells/search/polygon?points=32.81,-104.19;32.66,-104.32;...

SynMax Python Take-Home Architecture Plan

Page 11

GET /health response:

{"status": "ok"}

GET /well/{api\_number} response:

{

"api": "30-015-25325",

"operator": "...",

"status": "...",

"well\_type": "...",

"work\_type": "...",

"directional\_status": "...",

"multi\_lateral": "...",

"mineral\_owner": "...",

"surface\_owner": "...",

"surface\_location": "...",

"gl\_elevation": 3512,

"kb\_elevation": null,

"df\_elevation": null,

"single\_multiple\_completion": "...",

"potash\_waiver": "...",

"spud\_date": "1998-01-10",

"last\_inspection": "2024-04-30",

"tvd": 8500,

"latitude": 32.75,

"longitude": -104.12,

"crs": "NAD83"

}

If the API number is not found:

{"detail": "Well API number not found"}

with HTTP status 404.

Polygon endpoint response:

{

"count": 42,

"api\_numbers": \[\
\
"30-015-25325",\
\
"30-015-25327"\
\
\]

}

For strict assignment compatibility, the endpoint can also support a bare-array mode:

GET /wells/search/polygon?points=...&amp;format=array

returning:

\["30-015-25325", "30-015-25327"\]

# Geospatial Search Design

SynMax Python Take-Home Architecture Plan

Page 12

The polygon endpoint receives latitude/longitude pairs.

Important convention:

The assignment provides points as (latitude, longitude).

Most GIS libraries use (longitude, latitude) or (x, y).

Be explicit in code and documentation.

Algorithm:

1.

Parse the points query parameter.

2.

Validate at least three unique vertices.

3.

Validate latitude and longitude ranges.

4.

Ensure the polygon is closed. If first point does not equal last point, append the first point.

5.

Compute min/max latitude and longitude.

6.

Query SQLite for candidate wells inside that bounding box.

7.

Run a point-in-polygon check for exact inclusion.

8.

Include boundary points as inside.

9.

Sort API numbers so output is deterministic.

SQL prefilter:

SELECT "API", "Latitude", "Longitude"

FROM api\_well\_data

WHERE "Latitude" BETWEEN :min\_lat AND :max\_lat

AND "Longitude" BETWEEN :min\_lon AND :max\_lon

AND "Latitude" IS NOT NULL

AND "Longitude" IS NOT NULL;

Why not use PostGIS:

The assignment requires SQLite.

The dataset is only 480 rows.

A tested pure-Python point-in-polygon function is enough.

What to say for production:

In production, move to Postgres/PostGIS.

Store a real geometry(Point, 4326) column.

Use ST\_Contains or ST\_Covers.

Add a GiST index.

# Polygon CSV Output

Required output command:

SynMax Python Take-Home Architecture Plan

Page 13

python -m app.cli polygon-csv \

-db data/sqlite.db \

-points "32.81,-104.19;32.66,-104.32;32.54,-104.24;32.50,-104.03;32.73,-104.01;32.79,-103

.91;32.84,-104.05;32.81,-104.19" \

-out outputs/polygon\_results.csv

Expected CSV format:

api

30-015-25325

30-015-25327

The CSV should be generated from the same service function used by the API endpoint. That avoids one logic path for

the API and a different logic path for the output file.

# Testing Strategy

Minimum tests:

CSV validation accepts all 480 input rows.

CSV validation rejects malformed API numbers.

Parser extracts all required fields from a saved fixture.

Parser detects a Turnstile/human-verification page and returns a clear source error.

Database upsert inserts a new row.

Database upsert updates an existing row without duplication.

GET /well/{api} returns 200 for existing rows.

GET /well/{api} returns 404 for missing rows.

Polygon parser rejects malformed polygons.

Point-in-polygon includes inside points.

Point-in-polygon excludes outside points.

Point-in-polygon treats boundary points consistently.

Polygon endpoint returns deterministic sorted API numbers.

Recommended test command:

pytest -q

Recommended lint command:

ruff check app tests

# Local Run Commands For README

SynMax Python Take-Home Architecture Plan

Page 14

The README should be copy-paste friendly.

python -m venv .venv

source .venv/bin/activate

python -m pip install --upgrade pip

python -m pip install -e ".\[dev\]"

Initialize the database:

python -m app.cli init-db --db data/sqlite.db

Ingest the CSV:

python -m app.cli ingest --csv data/apis\_pythondev\_test.csv --db data/sqlite.db

Run tests:

pytest -q

Start the API:

uvicorn app.main:app --reload --port 8000

Try one well:

curl http://127.0.0.1:8000/well/30-015-25325

Try the polygon search:

curl "http://127.0.0.1:8000/wells/search/polygon?points=32.81,-104.19;32.66,-104.32;32.54,-1

04.24;32.50,-104.03;32.73,-104.01;32.79,-103.91;32.84,-104.05;32.81,-104.19"

Generate the required CSV:

python -m app.cli polygon-csv \

-points "32.81,-104.19;32.66,-104.32;32.54,-104.24;32.50,-104.03;32.73,-104.01;32.79,-103

.91;32.84,-104.05;32.81,-104.19" \

-out outputs/polygon\_results.csv

# Pros And Cons Of Major Decisions

FastAPI Instead Of Flask

Pros:

Type-friendly and modern.

Automatic OpenAPI docs at /docs.

SynMax Python Take-Home Architecture Plan

Page 15

Strong request validation with Pydantic.

Good signal for an API-first Python role.

Cons:

Slightly more framework concepts to learn.

Async support can be confusing if mixed poorly with sync database code.

Decision:

Use FastAPI, but keep route handlers simple and push logic into service functions.

SQLAlchemy Instead Of Raw sqlite3

Pros:

Cleaner mapping between awkward SQL column names and Python attributes.

Easier future migration to Postgres.

Safer parameterized SQL patterns.

Cons:

More abstraction for a small project.

You need to understand sessions/engines enough to explain them.

Decision:

Use SQLAlchemy Core or a lightweight ORM mapping. Avoid overengineering relationships because there is only one

required data table.

Exact SQL Column Names Instead Of Snake Case In SQLite

Pros:

Directly satisfies the take-home wording.

Easier for evaluator to inspect the SQLite database.

Reduces risk of failing on a technicality.

Cons:

SQL queries require quoted identifiers.

Column names are less pleasant in Python.

Decision:

Keep exact SQLite column names and map them to Pythonic keys in SQLAlchemy.

SynMax Python Take-Home Architecture Plan

Page 16

SQLite Instead Of Postgres

Pros:

Required by assignment.

Simple to run locally.

Easy to include sqlite.db in the repo.

Cons:

No native production-grade geospatial indexing.

Limited concurrent write behavior.

Less representative of SynMax's production Postgres stack.

Decision:

Use SQLite for the take-home and explicitly describe the Postgres/PostGIS migration path.

Pure Python Point-In-Polygon Instead Of Shapely

Pros:

No compiled geospatial dependency.

Easy for a reviewer to run.

Easy to test and explain.

Adequate for 480 records.

Cons:

Less robust for complex geometries, holes, self-intersections, and geodesic edge cases.

Not the production answer for large spatial datasets.

Decision:

Use bounding-box SQL plus a tested pure-Python polygon function for the take-home.

Mention PostGIS as the production upgrade.

Async HTTP Fetching Instead Of Sequential Requests

Pros:

Faster for hundreds of pages.

Shows modern Python capability.

Timeouts and retries are easier to centralize with httpx.

SynMax Python Take-Home Architecture Plan

Page 17

Cons:

Too much concurrency can look impolite to a public site.

Async code is harder for a Python beginner to debug.

Decision:

Use httpx.AsyncClient with conservative concurrency and backoff.

Keep parsing and database writes straightforward.

Replaceable Source Adapter Instead Of Hard-Coded Scraper

Pros:

Handles the current WellDetails layout/gating risk.

Lets tests use fixture data.

Lets a future official API source replace scraping without touching the API layer.

Cons:

Slightly more code than a one-file scraper.

Must avoid making the project feel abstract for abstraction's sake.

Decision:

Use a small adapter protocol with two or three concrete sources.

Explain this as risk containment, not overengineering.

# Five-Day Build Plan

Day 1: Project Skeleton, Schema, And Source Recon

Goals:

Create Git repo and Python project structure.

Copy the input CSV into data/.

Confirm CSV row count, format, duplicates, and county distribution.

Write SQL DDL and database initialization command.

Create the Pydantic WellRecord model.

Create a minimal FastAPI app with /health.

Save one or two source HTML fixtures if available.

Decide how to handle the current website change and document it in the README.

SynMax Python Take-Home Architecture Plan

Page 18

Deliverables:

pyproject.toml

app/main.py

app/db.py

app/models.py

app/schemas.py

app/cli.py

data/apis\_pythondev\_test.csv

passing init-db

first README draft

What you need to understand:

The database is the contract between ingestion and API.

API is the unique key.

We separate source fetching from parsing because websites change.

Day 2: Scraper, Parser, And Loader

Goals:

Implement CSV reading and API number validation.

Implement WellSource adapter.

Implement the WellDetails HTML fetcher.

Implement Turnstile/gated-page detection.

Implement parser field mapping and data normalization.

Implement idempotent upsert.

Run ingestion for all 480 rows or document blocked-source handling.

Produce a DB quality summary.

Deliverables:

app/scraper/client.py

app/scraper/parser.py

app/scraper/load.py

app/services/well\_repository.py

data/sqlite.db

parser tests

loader tests

SynMax Python Take-Home Architecture Plan

Page 19

What you need to understand:

Fetching gets raw source data.

Parsing turns source data into a normalized record.

Validation catches bad data before it hits SQL.

Upsert makes repeated runs safe.

Day 3: API And Geospatial Endpoint

Goals:

Implement GET /well/{api\_number}.

Implement polygon query parsing.

Implement bounding-box SQL candidate search.

Implement point-in-polygon filtering.

Implement GET /wells/search/polygon.

Add API tests with FastAPI TestClient.

Add the CLI command that generates outputs/polygon\_results.csv.

Deliverables:

app/services/geometry.py

API endpoint tests

outputs/polygon\_results.csv

working local API at http://127.0.0.1:8000

What you need to understand:

SQL does the cheap prefilter.

Python does the exact polygon check.

The same service function powers the API and CSV output.

Day 4: Quality, Documentation, And Optional Visualization

Goals:

Improve error messages.

Add logging.

Add ruff linting.

Run a clean rebuild from scratch.

Document all local commands.

Write a short architecture section in README.

SynMax Python Take-Home Architecture Plan

Page 20

Add an optional lightweight visual explorer only if the core work is done.

Optional visualization:

A tiny FastAPI-served HTML page at /explore.

Lets reviewer enter polygon points.

Shows result count and API numbers.

Uses no build system or heavy frontend unless time remains.

Deliverables:

polished README

tests passing

optional /explore

clean command transcript for demo

What you need to understand:

The README is part of the product.

A reviewer should be able to clone, run, test, and understand the project quickly.

Day 5: Final Verification And Presentation Prep

Goals:

Delete and recreate the database from scratch using documented commands.

Re-run ingestion.

Re-run tests and lint.

Start the API and manually call both required endpoints.

Regenerate polygon CSV.

Inspect SQLite table and row count.

Push to a public GitHub repository.

Prepare a 5-minute explanation.

Final checklist:

data/sqlite.db exists.

api\_well\_data exists.

Required columns exist exactly.

No duplicate APIs.

/well/{api} works.

Polygon endpoint works.

SynMax Python Take-Home Architecture Plan

Page 21

outputs/polygon\_results.csv exists.

README has setup and run instructions.

Tests pass.

Public repo URL is ready to send.

# Presentation Talking Points

Use this structure when presenting:

1.

Problem framing:

"The task has two parts: create a reliable local well-data read model, then expose it through an API."

2.

Architecture:

"I separated ingestion, parsing, storage, API, and geospatial logic so each part can be tested and replaced

independently."

3.

SQL decision:

"The SQLite table uses the exact required column names for assignment compatibility, while the Python model uses

clean snake\_case names through SQLAlchemy mapping."

4.

Data quality:

"The input had 480 valid unique API numbers. The ingestion validates format, converts types, stores nulls for missing

values, and uses idempotent upserts."

5.

Upstream website change:

"The NM OCD site changed after the assignment was written and now recommends official API access. I treated the

upstream source as an adapter so the rest of the system is stable whether the data comes from scraped HTML, an

approved API, or test fixtures."

6.

API:

"FastAPI gives typed validation and OpenAPI docs. The single-well endpoint is a direct primary-key lookup."

7.

Polygon search:

"The polygon endpoint first filters by bounding box in SQL, then applies a tested point-in-polygon function in Python. In

production I would move this to Postgres/PostGIS."

8.

Tradeoff awareness:

"SQLite and pure-Python geometry are correct for this take-home. For SynMax-scale geospatial workloads, I would

migrate to Postgres/PostGIS, scheduled ingestion, and cloud deployment."

# Questions You Should Be Ready To Answer

Why not just write one scraper script?

SynMax Python Take-Home Architecture Plan

Page 22

Because the assignment also asks for an API, and source pages can change. Separating the layers makes the code

testable and maintainable.

Why keep awkward SQL column names with spaces?

Because the assignment explicitly lists those names. SQLAlchemy lets the database satisfy the requirement while

Python remains clean.

Why use SQLite if SynMax uses Postgres?

SQLite is required for submission. The repository still uses SQL practices that migrate cleanly to Postgres.

Why not use PostGIS?

PostGIS is the production choice, but the deliverable is a local SQLite project with only 480 rows. Bounding-box SQL

plus tested Python geometry is appropriate here.

What happens if the scraper is blocked?

The code detects the blocked page and reports it clearly. It does not bypass human-verification systems. The source

adapter can be switched to the official EMNRD API or a SynMax-approved fixture/export.

How do you know the polygon endpoint is correct?

Unit tests cover inside, outside, and boundary points. The API and CSV generator use the same geometry service, so

there is one source of truth.

How would this scale?

Move SQLite to Postgres/PostGIS, put ingestion behind a scheduled Cloud Run job or Cloud Scheduler task, use

structured logs, track source fetch status in audit tables, and expose the API behind Cloud Run or GKE.

# Stretch Ideas Only After Core Requirements

These can make the project feel more polished, but only if the required project is already complete:

Add /stats endpoint with row counts, status counts, and missing coordinate counts.

Add /explore lightweight page to test polygon search visually.

Add a --limit option to ingestion for development.

Add a --source fixture mode for deterministic demos.

Add GitHub Actions running tests and lint.

Add a short architecture diagram in README.

Do not add a full React frontend unless the required Python project is already finished. The take-home is clearly

evaluating Python, SQL, scraping, and API quality.

SynMax Python Take-Home Architecture Plan

Page 23

# Definition Of Done

The project is done when a reviewer can run:

git clone &lt;repo-url&gt;

cd synmax-python-takehome

python -m venv .venv

source .venv/bin/activate

python -m pip install -e ".\[dev\]"

pytest -q

uvicorn app.main:app --reload --port 8000

and then successfully call:

curl http://127.0.0.1:8000/well/30-015-25325

and:

curl "http://127.0.0.1:8000/wells/search/polygon?points=32.81,-104.19;32.66,-104.32;32.54,-1

04.24;32.50,-104.03;32.73,-104.01;32.79,-103.91;32.84,-104.05;32.81,-104.19"

The repository should also include:

data/sqlite.db

outputs/polygon\_results.csv

tests

README

clear notes about source limitations if the current website blocks automated scraping

# What To Study Before Presenting

Focus on these concepts:

API number: the unique oil/gas well identifier, not a software API.

Scraper: code that fetches source data.

Parser: code that extracts fields from source data.

Pydantic model: code that validates and converts records.

Upsert: insert if new, update if already present.

Primary key: the unique database identifier.

Index: a structure that makes lookup/filtering faster.

Bounding box: a cheap rectangular prefilter before exact polygon math.

Point-in-polygon: the exact geometry check for whether a well is inside the search polygon.

FastAPI: the Python web framework serving customer endpoints.

OpenAPI docs: automatic API documentation generated by FastAPI.

SynMax Python Take-Home Architecture Plan

Page 24

# Recommended Final Message To SynMax

When sending the repo, keep the email short:

Hi Felix,

Thanks again for the take-home. Here is my public repository:

&lt;repo-url&gt;

The README includes setup instructions, ingestion commands, API usage, and notes on the

current NM OCD source behavior. The repo includes the populated SQLite database and the

polygon-results CSV requested in the prompt.

Best,

Athena

# Source Notes

Materials reviewed for this plan:

Local take-home PDF: /Users/athenanexis/Downloads/python\_dev\_candidate/SynMax Python Dev

Programming Takehome.pdf

Local input CSV: /Users/athenanexis/Downloads/python\_dev\_candidate/apis\_pythondev\_test.csv

NM OCD WellDetails example URL from assignment:

https://wwwapps.emnrd.nm.gov/OCD/OCDPermitting/Data/WellDetails.aspx?api=30-045-35432

NM OCD public pages noting the June 4, 2026 WellDetails layout update and automated API guidance.

EMNRD API homepage: https://api.emnrd.nm.gov/