# Story 17.10: Extract Trade Execution to Service

Status: done

## Story

As a developer,
I want trade execution logic extracted to `trade/service.py`,
So that the trade handler is thin routing and trade business logic is centralized.

## Acceptance Criteria

1. **AC1 — `execute_trade()` in service:**
   - Given: `_execute_trade()` (~114 lines), `_fail_trade()`, `_validate_offers()` in `trade.py` handler
   - Then: All three functions moved to `server/trade/service.py` (new file)
   - And: `_execute_trade()` in handler becomes thin delegation to `execute_trade()`

2. **AC2 — Tests pass:**
   - All 1066+ tests pass with updated imports

## Tasks / Subtasks

- [x] Task 1: Create `server/trade/service.py` (AC: #1)
  - [x] 1.1 Move `_validate_offers()`, `_fail_trade()`, `execute_trade()` to new file
  - [x] 1.2 Handler `_execute_trade()` becomes 3-line delegation

- [x] Task 2: Clean up unused imports in `trade.py` handler (AC: #1)
  - [x] 2.1 Removed unused `player_repo` import

- [x] Task 3: Update test imports (AC: #2)
  - [x] 3.1 `test_trade.py`: `_validate_offers` import changed to `server.trade.service`; `_execute_trade` stays from handler (thin wrapper)

- [x] Task 4: All 1066 tests pass (AC: #2)

## Dev Notes

### References
- [Source: _bmad-output/planning-artifacts/epics.md — Story 17.10]
- [Source: server/net/handlers/trade.py — original _execute_trade location]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Completion Notes List
- Created `server/trade/service.py` (~140 lines) with `execute_trade`, `_fail_trade`, `_validate_offers`
- Handler `_execute_trade` is now 3-line delegation
- Handler shrunk from ~486 to ~350 lines
- All 1066 tests pass

### File List
- `server/trade/service.py` (created)
- `server/net/handlers/trade.py` (modified — replaced 3 functions with delegation, removed player_repo import)
- `tests/test_trade.py` (modified — updated _validate_offers import)
