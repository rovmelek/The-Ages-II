# Story 17.4: Trade State Machine StrEnum

Status: done

## Story

As a developer,
I want trade session states defined as a `TradeState` StrEnum,
So that invalid state assignments are caught by type checkers and state names are IDE-autocomplete-friendly.

## Acceptance Criteria

1. **Given** 7 trade state strings scattered across `trade/manager.py`,
   **When** Story 17.4 is implemented,
   **Then** a `TradeState` StrEnum exists in `server/trade/session.py` with members `REQUEST_PENDING`, `NEGOTIATING`, `ONE_READY`, `BOTH_READY`, `EXECUTING`, `CANCELLED`, `COMPLETE`.

2. **Given** the `Trade` dataclass,
   **When** Story 17.4 is implemented,
   **Then** the `state` field type changes from `str` to `TradeState`.

3. **Given** 16 assignments and comparisons in `trade/manager.py`,
   **When** Story 17.4 is implemented,
   **Then** all use `TradeState` members.

4. **Given** outbound messages that include trade state,
   **When** Story 17.4 is implemented,
   **Then** wire protocol value is unchanged — StrEnum serializes as its string value (ADR-17-1).

5. **Given** all existing tests,
   **When** Story 17.4 is implemented,
   **Then** all tests pass.

## Tasks / Subtasks

- [x] Task 1: Create `TradeState` StrEnum in `trade/session.py` (AC: #1, #2)
  - [x] 1.1 Add `from enum import StrEnum` import
  - [x] 1.2 Define `TradeState(StrEnum)` with 7 members
  - [x] 1.3 Change `Trade.state` field type from `str` to `TradeState`

- [x] Task 2: Update all 16 state references in `trade/manager.py` (AC: #3)
  - [x] 2.1 Import `TradeState` from `server.trade.session`
  - [x] 2.2 Replace all 16 string literals with `TradeState` members

- [x] Task 3: Verify all tests pass (AC: #5)
  - [x] 3.1 Run `make test`

## Dev Notes

- ADR-17-1: StrEnum compares equal to strings — wire protocol unchanged
- 2 production files: `trade/session.py`, `trade/manager.py`

### References
- [Source: _bmad-output/planning-artifacts/epics.md — Story 17.4 AC]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Completion Notes List
- Created `TradeState` StrEnum with 7 members in `trade/session.py`
- Updated `Trade.state` field type from `str` to `TradeState`
- Replaced all 16 trade state string literals in `trade/manager.py`
- All 1066 tests pass (StrEnum equality preserves wire protocol)

### File List
- `server/trade/session.py` (modified)
- `server/trade/manager.py` (modified)
