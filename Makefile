.PHONY: test test-verbose server install db-migrate protocol-doc check-protocol

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

protocol-doc:
	.venv/bin/python scripts/generate_protocol_doc.py > _bmad-output/planning-artifacts/protocol-spec.md

check-protocol:
	@.venv/bin/python scripts/generate_protocol_doc.py > /tmp/protocol-spec-check.md
	@diff -q _bmad-output/planning-artifacts/protocol-spec.md /tmp/protocol-spec-check.md >/dev/null 2>&1 \
		&& echo "Protocol spec is up to date." \
		|| (echo "ERROR: protocol-spec.md is out of date. Run 'make protocol-doc' to regenerate." && exit 1)
