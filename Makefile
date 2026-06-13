.PHONY: start open-session close-session check-session scraping scraping-supervised load-db ingest ingest-supervised reset-ingest test lint

start:
	set -a; [ ! -f .env ] || . ./.env; set +a; .venv/bin/uvicorn app.main:app --reload

open-session:
	set -a; [ ! -f .env ] || . ./.env; set +a; .venv/bin/python -m app.cli open-session

close-session:
	set -a; [ ! -f .env ] || . ./.env; set +a; .venv/bin/python -m app.cli close-session

check-session:
	set -a; [ ! -f .env ] || . ./.env; set +a; .venv/bin/python -m app.cli check-session

scraping:
	set -a; [ ! -f .env ] || . ./.env; set +a; .venv/bin/python -m app.cli scrape-wells

scraping-supervised:
	set -a; [ ! -f .env ] || . ./.env; set +a; .venv/bin/python -m app.cli scrape-wells-supervised

load-db:
	set -a; [ ! -f .env ] || . ./.env; set +a; .venv/bin/python -m app.cli load-db --replace

ingest: scraping load-db

ingest-supervised: scraping-supervised load-db

reset-ingest:
	rm -f data/firecrawl_browser_session.json data/api_well_data_scraped.csv data/scrape_report.json data/scrape_checkpoint.json
	[ ! -f api_well_data.db ] || sqlite3 -cmd '.timeout 10000' api_well_data.db 'DELETE FROM api_well_data;' || (echo 'api_well_data.db is locked. Stop make start, DB viewers, or other ingest/load processes, then retry.' && exit 1)

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check .
