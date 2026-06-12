.PHONY: start open-session close-session check-session scraping load-db ingest test lint

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

load-db:
	set -a; [ ! -f .env ] || . ./.env; set +a; .venv/bin/python -m app.cli load-db --replace

ingest: scraping load-db

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check .
