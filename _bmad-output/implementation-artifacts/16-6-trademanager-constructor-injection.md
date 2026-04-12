# Story 16.6: TradeManager Constructor Injection

Status: done

## Story

As a **server developer**,
I want `TradeManager` to use constructor injection for `connection_manager`,
So that all managers follow the same DI pattern (`PartyManager` already uses constructor injection).

## Acceptance Criteria

1. **Given** `TradeManager.__init__` takes no arguments and `set_connection_manager` is called separately,
   **When** Story 16.6 is implemented,
   **Then** `TradeManager.__init__` takes `connection_manager` as keyword argument,
   **And** `set_connection_manager` method is removed,
   **And** `server/app.py` creates `TradeManager(connection_manager=self.connection_manager)`.

2. **Given** all 959+ existing tests,
   **When** Story 16.6 is implemented,
   **Then** all tests pass (test files constructing `TradeManager` updated to pass `connection_manager`).

## Tasks / Subtasks

- [x] Task 1: Update `TradeManager.__init__` (AC: #1)
  - [x] 1.1: Add `connection_manager` keyword argument with `None` default
  - [x] 1.2: Remove `set_connection_manager` method
  - [x] 1.3: Update docstring

- [x] Task 2: Update `server/app.py` (AC: #1)
  - [x] 2.1: Replace `TradeManager()` + `set_connection_manager` with single `TradeManager(connection_manager=...)`

- [x] Task 3: Update test files (AC: #2)
  - [x] 3.1: Update 25 `TradeManager()` calls in test files (no-arg stays since default is None)
  - [x] 3.2: Remove 2 `set_connection_manager` calls in `test_trade.py` — pass via constructor instead

- [x] Task 4: Run full test suite (AC: #2)
  - [x] 4.1: Run `make test` — all 959+ tests pass

## Dev Notes

- Matches `PartyManager(connection_manager=...)` pattern (Story 15.4)
- Most tests don't need `connection_manager` (they don't test timeout notifications), so `None` default is fine
- Only 2 tests (`test_trade.py:269`, `test_trade.py:287`) call `set_connection_manager` — these need constructor injection instead

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Completion Notes List
- Changed `TradeManager.__init__` to accept `connection_manager` kwarg
- Removed `set_connection_manager` method
- Updated `app.py` to single-line construction
- Updated 2 tests that called `set_connection_manager`
- 959 tests pass

### File List
- `server/trade/manager.py` — Modified: constructor injection, removed setter
- `server/app.py` — Modified: single-line TradeManager construction
- `tests/test_trade.py` — Modified: constructor injection in 2 tests
