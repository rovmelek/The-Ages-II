# Story 15.6: EventBus Resilience & Config Gaps

Status: done

## Story

As a developer,
I want the EventBus to isolate subscriber failures, and remaining unconfigurable constants to be in `Settings`,
So that one broken subscriber cannot crash the emit loop and all operational constants are environment-overridable.

## Acceptance Criteria

1. **Given** `EventBus.emit()` in `server/core/events.py` (lines 18-21) iterates subscribers with no error isolation:
   ```python
   async def emit(self, event_type: str, **data: Any) -> None:
       for cb in self._subscribers.get(event_type, []):
           await cb(**data)
   ```
   **When** Story 15.6 is implemented,
   **Then** each subscriber callback is wrapped in `try/except Exception` with `logger.exception(...)` logging,
   **And** remaining subscribers are still called even if one raises,
   **And** a new test verifies: subscriber A raises → subscriber B still executes.

2. **Given** `_RARE_CHECK_INTERVAL = 60` in `server/core/scheduler.py` (line 28) is a module-level constant,
   **When** Story 15.6 is implemented,
   **Then** `Settings` in `server/core/config.py` gains `RARE_CHECK_INTERVAL_SECONDS: int = 60`,
   **And** `Scheduler._loop()` references `settings.RARE_CHECK_INTERVAL_SECONDS` instead of `_RARE_CHECK_INTERVAL`,
   **And** the module-level `_RARE_CHECK_INTERVAL` constant is removed.

3. **Given** `RoomState.mob_states` field in `server/room/models.py` (line 28) is a JSON column never written with actual mob data (only initialized as `{}` in `server/room/objects/state.py` line 82),
   **When** Story 15.6 is implemented,
   **Then** the field is removed from `RoomState` model,
   **And** the `mob_states={}` kwarg is removed from the `RoomState(...)` constructor call in `state.py`,
   **And** an Alembic migration drops the `mob_states` column (SQLite 3.51.0 supports `DROP COLUMN` natively — no `batch_alter_table` needed).

4. **Given** all existing tests (807+),
   **When** Story 15.6 is implemented,
   **Then** all tests pass; one new test added for EventBus error isolation.

## Tasks / Subtasks

- [x] Task 1: Add error isolation to `EventBus.emit()` (AC: #1)
  - [x] 1.1: Add `import logging` and `logger = logging.getLogger(__name__)` to `server/core/events.py`
  - [x] 1.2: Wrap each `await cb(**data)` in `try/except Exception` with `logger.exception`
  - [x] 1.3: Add test `test_emit_subscriber_error_isolation` to `tests/test_events.py` in `TestEventBus` class — subscriber A raises `RuntimeError`, subscriber B still called

- [x] Task 2: Move `_RARE_CHECK_INTERVAL` to `Settings` (AC: #2)
  - [x] 2.1: Add `RARE_CHECK_INTERVAL_SECONDS: int = 60` to `Settings` in `server/core/config.py`
  - [x] 2.2: In `server/core/scheduler.py`, import `settings` from `server.core.config`, replace `_RARE_CHECK_INTERVAL` usage in `_loop()` with `settings.RARE_CHECK_INTERVAL_SECONDS`, remove the module-level constant

- [x] Task 3: Remove `RoomState.mob_states` (AC: #3)
  - [x] 3.1: Remove `mob_states` field from `RoomState` in `server/room/models.py` (line 28)
  - [x] 3.2: Remove `mob_states={}` kwarg from `RoomState(...)` constructor in `server/room/objects/state.py` (line 82)
  - [x] 3.3: Update `tests/test_repos.py` `test_room_state_save_and_get` (lines 129-140): remove `mob_states` kwarg from `RoomState(...)` constructor and remove `assert found.mob_states == ...` assertion
  - [x] 3.4: Create Alembic migration: `alembic revision --autogenerate -m "drop room_states mob_states column"` — verify it generates `op.drop_column('room_states', 'mob_states')` in upgrade and re-adds the column in downgrade

- [x] Task 4: Verify all tests pass (AC: #4)
  - [x] 4.1: Run `make test` — all 808 tests pass (807 existing + 1 new), 0 failures, 0 warnings

## Dev Notes

### EventBus Error Isolation Pattern

Current code in `server/core/events.py` (22 lines total):
- `emit()` at lines 18-21: simple `for cb in subscribers: await cb(**data)` — no try/except
- Add `logging` import at top, `logger` at module level
- Wrap the await in try/except, log with `logger.exception(f"EventBus subscriber error on {event_type}")` — this logs the full traceback

The new test should:
1. Create an EventBus
2. Subscribe two handlers: A raises `RuntimeError`, B appends to a list
3. `await bus.emit(event_type)` 
4. Assert B's list was populated (proving it wasn't skipped)

Existing test class: `TestEventBus` in `tests/test_events.py` (line 20) — add the new test there.

### Scheduler Config Migration

`_RARE_CHECK_INTERVAL = 60` at line 28 of `server/core/scheduler.py`. Only usage is in `_loop()` at line 124: `await asyncio.sleep(_RARE_CHECK_INTERVAL)`.

`settings` import pattern — `scheduler.py` already imports from `server.room.*`; add `from server.core.config import settings` at the top-level imports (before the `TYPE_CHECKING` block).

### mob_states Column Removal

**Files to change:**
- `server/room/models.py` line 28: delete `mob_states: Mapped[dict] = mapped_column(JSON, default=dict)`
- `server/room/objects/state.py` line 82: change `RoomState(room_key=room_key, mob_states={}, dynamic_state={})` → `RoomState(room_key=room_key, dynamic_state={})`

**Alembic migration:** Run `alembic revision --autogenerate -m "drop room_states mob_states column"` from project root. SQLite 3.51.0 supports native `DROP COLUMN` — no `batch_alter_table` wrapper needed. Verify the auto-generated migration has the correct `op.drop_column` / `op.add_column` pair.

**Test references:** `tests/test_repos.py` lines 129-140 (`test_room_state_save_and_get`) creates a `RoomState` with `mob_states={"goblin_1": {"alive": True}}` and asserts `found.mob_states == {"goblin_1": {"alive": True}}`. Both the constructor kwarg and the assertion must be removed.

### Anti-Patterns to Avoid

- Do NOT change any gameplay behavior — pure refactor + resilience improvement
- Do NOT change assertion values in any existing test
- Do NOT use bare `except:` — always `except Exception:` to avoid catching `KeyboardInterrupt`/`SystemExit`
- Do NOT add retry logic to EventBus — ADR-15-6 says log-and-continue only
- Do NOT use `batch_alter_table` — SQLite version is 3.51.0 (≥ 3.35.0)
- All modified files MUST have `from __future__ import annotations` as the first import — project convention
- Use `make test` to run tests, never bare `pytest`

### Project Structure Notes

- `server/core/events.py` — EventBus (22 lines, minimal file)
- `server/core/scheduler.py` — Scheduler with `_RARE_CHECK_INTERVAL` constant
- `server/core/config.py` — `Settings` class (Pydantic `BaseSettings`)
- `server/room/models.py` — SQLAlchemy models including `RoomState`
- `server/room/objects/state.py` — Room object state persistence (uses `RoomState`)
- `alembic/versions/` — one existing migration: `bf6901ef8aa9_initial_schema.py`
- `tests/test_events.py` — EventBus tests (class `TestEventBus` at line 20)

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Story 15.6 (lines 3843-3879)]
- [Source: server/core/events.py — EventBus.emit() (lines 18-21)]
- [Source: server/core/scheduler.py — _RARE_CHECK_INTERVAL (line 28), _loop() (lines 119-126)]
- [Source: server/core/config.py — Settings class (lines 9-136)]
- [Source: server/room/models.py — RoomState.mob_states (line 28)]
- [Source: server/room/objects/state.py — RoomState constructor (line 82)]
- [Source: tests/test_repos.py — test_room_state_save_and_get (lines 125-140), mob_states usage]
- [Source: alembic/versions/bf6901ef8aa9_initial_schema.py — existing migration pattern]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- All 808 tests pass (0 failures, 0 warnings, ~3.8s)
- Pre-existing flaky test in `test_integration.py` (different test fails each run, passes in isolation) — not related to this story

### Completion Notes List

- Added error isolation to `EventBus.emit()` — each subscriber wrapped in `try/except Exception` with `logger.exception`, remaining subscribers still called on failure
- Added `test_emit_subscriber_error_isolation` test verifying bad subscriber doesn't prevent good subscriber from running
- Moved `_RARE_CHECK_INTERVAL = 60` from module-level constant in `scheduler.py` to `Settings.RARE_CHECK_INTERVAL_SECONDS` in `config.py`
- Removed `RoomState.mob_states` column — field removed from model, constructor kwarg removed from `state.py`, test assertions updated in `test_repos.py`
- Created Alembic migration `70a9c771b610_drop_room_states_mob_states_column.py` — drops `mob_states` column (upgrade) / re-adds it (downgrade)
- Pure refactor + resilience improvement — zero gameplay behavior changes

### File List

**Modified:**
- `server/core/events.py` — Added logging import and try/except error isolation in `emit()`
- `server/core/scheduler.py` — Replaced `_RARE_CHECK_INTERVAL` with `settings.RARE_CHECK_INTERVAL_SECONDS`
- `server/core/config.py` — Added `RARE_CHECK_INTERVAL_SECONDS: int = 60` to `Settings`
- `server/room/models.py` — Removed `mob_states` field from `RoomState`
- `server/room/objects/state.py` — Removed `mob_states={}` kwarg from `RoomState()` constructor
- `tests/test_events.py` — Added `test_emit_subscriber_error_isolation` test
- `tests/test_repos.py` — Removed `mob_states` from `test_room_state_save_and_get`

**New:**
- `alembic/versions/70a9c771b610_drop_room_states_mob_states_column.py` — Migration to drop `mob_states` column
