# ISS-013: Add Makefile test runner script

**Severity:** Low (developer friction)
**Found during:** Epic 10 retrospective, carried through Epic 11 retrospective
**Date:** 2026-04-11

## Problem

Running tests requires `.venv/bin/python -m pytest tests/` because the system Python (3.9) lacks project dependencies and the fbcode Python (3.12) has SSL cert issues with pip. This is documented in CLAUDE.md and enforced by a pre-tool hook, but every story's dev notes mention the friction. The issue has been an open action item across two retrospectives.

## Proposed Fix

Add a `Makefile` with common development targets:

```makefile
.PHONY: test test-verbose server install

test:
	.venv/bin/python -m pytest tests/ -q --tb=short

test-verbose:
	.venv/bin/python -m pytest tests/ -v --tb=short

server:
	.venv/bin/python run.py

install:
	.venv/bin/pip install -e ".[dev]"
```

This gives:
- `make test` — quick test run
- `make test-verbose` — verbose test run with test names
- `make server` — start the server
- `make install` — install dependencies

## Impact

- 1 new file: `Makefile`
- No code changes
- No test changes

## Verification

- `make test` runs the full test suite using the venv Python
- All 601 tests pass
