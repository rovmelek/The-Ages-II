# Story 17.3: Unify Direction Strings

Status: done

## Story

As a developer,
I want direction strings defined in one place and imported everywhere,
So that adding a new direction requires one change instead of three.

## Acceptance Criteria

1. **Given** `DIRECTION_DELTAS` in `room/room.py` as the authoritative source and `_SCAN_OFFSETS` in `query.py` independently defining the same 4 directions,
   **When** Story 17.3 is implemented,
   **Then** `query.py` imports `DIRECTION_DELTAS` from `server.room.room` and derives `_SCAN_OFFSETS` from it (plus the `"here"` entry).

2. **Given** the schema validator in `schemas.py` independently checking `("up", "down", "left", "right")`,
   **When** Story 17.3 is implemented,
   **Then** `MoveMessage.validate_direction` imports `DIRECTION_DELTAS` and validates against its keys.

3. **Given** all existing tests,
   **When** Story 17.3 is implemented,
   **Then** all tests pass unchanged.

## Tasks / Subtasks

- [x] Task 1: Update `query.py` to derive `_SCAN_OFFSETS` from `DIRECTION_DELTAS` (AC: #1)
  - [x] 1.1 Import `DIRECTION_DELTAS` from `server.room.room`
  - [x] 1.2 Replace hardcoded `_SCAN_OFFSETS` with: `_SCAN_OFFSETS = [(0, 0, "here")] + [(dx, dy, d) for d, (dx, dy) in DIRECTION_DELTAS.items()]`

- [x] Task 2: Update `schemas.py` to validate against `DIRECTION_DELTAS` (AC: #2)
  - [x] 2.1 Import `DIRECTION_DELTAS` from `server.room.room`
  - [x] 2.2 Replace `v not in ("up", "down", "left", "right")` with `v not in DIRECTION_DELTAS`

- [x] Task 3: Verify all tests pass (AC: #3)
  - [x] 3.1 Run `make test`

## Dev Notes

- No circular import risk: `net/schemas.py` has no existing imports from `room/`, but `net/handlers/` already imports from `room/`
- `DIRECTION_DELTAS` is a module-level dict in `room.py` — importing it at module level is safe

### References
- [Source: _bmad-output/planning-artifacts/epics.md — Story 17.3 AC]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Completion Notes List
- `query.py` now derives `_SCAN_OFFSETS` from `DIRECTION_DELTAS` import
- `schemas.py` `MoveMessage.validate_direction` validates against `DIRECTION_DELTAS.keys()`
- All 1066 tests pass

### File List
- `server/net/handlers/query.py` (modified)
- `server/net/schemas.py` (modified)
