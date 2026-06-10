.PHONY: start test lint

start:
	set -a; . ./.env; set +a; .venv/bin/uvicorn app.api:app --reload

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check .
