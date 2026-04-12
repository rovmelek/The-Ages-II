.PHONY: test test-verbose server install db-migrate

test:
	.venv/bin/python -m pytest tests/ -q --tb=short

test-verbose:
	.venv/bin/python -m pytest tests/ -v --tb=short

server:
	.venv/bin/python run.py

install:
	.venv/bin/pip install -e ".[dev]"

db-migrate:
	.venv/bin/alembic upgrade head
