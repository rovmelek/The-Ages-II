# Story 17.5: PostgreSQL Dependency & Alembic Portability

Status: done

## Story

As a developer,
I want `asyncpg` available as an optional dependency and the Alembic migration portable,
So that switching to PostgreSQL requires only setting `DATABASE_URL`.

## Acceptance Criteria

1. **Given** `pyproject.toml` lists only `aiosqlite>=0.19.0`,
   **When** Story 17.5 is implemented,
   **Then** `asyncpg>=0.29.0` is added under `[project.optional-dependencies]` with key `postgres`.

2. **Given** the Alembic migration `70a9c771b610_*.py` uses `sqlite.JSON()` in `downgrade()`,
   **When** Story 17.5 is implemented,
   **Then** `sqlite.JSON()` is replaced with `sa.JSON()` and the sqlite dialect import is removed.

3. **Given** all existing tests,
   **When** Story 17.5 is implemented,
   **Then** all tests pass — `aiosqlite` remains the default driver.

## Tasks / Subtasks

- [x] Task 1: Add asyncpg optional dependency (AC: #1)
  - [x] 1.1 Add `postgres = ["asyncpg>=0.29.0"]` to `[project.optional-dependencies]` in `pyproject.toml`

- [x] Task 2: Fix Alembic migration portability (AC: #2)
  - [x] 2.1 In `alembic/versions/70a9c771b610_drop_room_states_mob_states_column.py`: replace `sqlite.JSON()` with `sa.JSON()`
  - [x] 2.2 Remove `from sqlalchemy.dialects import sqlite` import

- [x] Task 3: Verify all tests pass (AC: #3)
  - [x] 3.1 Run `make test`

## Dev Notes

- 2 files: `pyproject.toml`, `alembic/versions/70a9c771b610_*.py`

### References
- [Source: _bmad-output/planning-artifacts/epics.md — Story 17.5 AC]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Completion Notes List
- Added `postgres = ["asyncpg>=0.29.0"]` optional dependency
- Replaced `sqlite.JSON()` with `sa.JSON()` in Alembic migration downgrade
- Removed `from sqlalchemy.dialects import sqlite` import
- All 1066 tests pass

### File List
- `pyproject.toml` (modified)
- `alembic/versions/70a9c771b610_drop_room_states_mob_states_column.py` (modified)
