# Story 15.7: Data Layer Consistency

Status: done

## Story

As a developer,
I want the SpawnCheckpoint data access to follow the repo pattern,
So that the data layer is consistent across all persistable entities.

## Acceptance Criteria

1. **Given** `SpawnCheckpoint` queries are inlined directly in `Scheduler._run_rare_spawn_checks()` (lines 146-161 of `server/core/scheduler.py`) and `_recover_checkpoints()` (lines 210-224) using raw `select(SpawnCheckpoint)`, `session.add(SpawnCheckpoint(...))`, and `session.execute(...)`,
   **When** Story 15.7 is implemented,
   **Then** a `server/room/spawn_repo.py` module exists with functions:
   - `get_checkpoint(session, room_key, npc_key) -> SpawnCheckpoint | None`
   - `upsert_checkpoint(session, room_key, npc_key, **kwargs) -> SpawnCheckpoint`
   - `get_all_checkpoints(session) -> list[SpawnCheckpoint]`
   **And** `Scheduler` uses these repo functions instead of inline queries.

2. **Given** existing repo modules (`server/player/repo.py`, `server/room/repo.py`, `server/items/item_repo.py`, `server/combat/cards/card_repo.py`) follow the pattern: module-level async functions taking `session: AsyncSession` as first parameter, no `session.commit()` calls (transaction manager handles it),
   **When** Story 15.7 is implemented,
   **Then** `spawn_repo.py` follows the same pattern exactly.

3. **Given** all existing tests (808),
   **When** Story 15.7 is implemented,
   **Then** all tests pass with no assertion value changes.

4. **Given** the Epic 15 Definition of Done requires: no direct `select(SpawnCheckpoint)` or `session.add(SpawnCheckpoint(...))` in `scheduler.py` — all access via `spawn_repo`,
   **When** Story 15.7 is implemented,
   **Then** `scheduler.py` has zero `select()` imports and zero `SpawnCheckpoint` model imports — it imports only from `spawn_repo`.

## Tasks / Subtasks

- [x] Task 1: Create `server/room/spawn_repo.py` (AC: #1, #2)
  - [x] 1.1: Create module with `from __future__ import annotations` as first import
  - [x] 1.2: Implement `get_checkpoint(session: AsyncSession, room_key: str, npc_key: str) -> SpawnCheckpoint | None` — `select(SpawnCheckpoint).where(room_key==, npc_key==)` then `scalar_one_or_none()`
  - [x] 1.3: Implement `upsert_checkpoint(session: AsyncSession, room_key: str, npc_key: str, **kwargs) -> SpawnCheckpoint` — query existing, update or create+flush; returns the checkpoint so caller can mutate fields (next_check_at, currently_spawned, last_check_at)
  - [x] 1.4: Implement `get_all_checkpoints(session: AsyncSession) -> list[SpawnCheckpoint]` — `select(SpawnCheckpoint)` then `scalars().all()`

- [x] Task 2: Refactor `Scheduler._run_rare_spawn_checks()` (AC: #1, #4)
  - [x] 2.1: Replace both the inline `select(SpawnCheckpoint).where(...)` query (lines 146-152) AND the `if cp is None: SpawnCheckpoint(...)` create block (lines 153-161) with a single `spawn_repo.upsert_checkpoint(session, room_key, npc_key, next_check_at=now, currently_spawned=False)` call — returns existing checkpoint or creates new one
  - [x] 2.2: Keep field mutations (`cp.last_check_at = now`, `cp.next_check_at = ...`, `cp.currently_spawned = True`) on the returned checkpoint object — same as other repo usage patterns (e.g., `room_repo.upsert_room` returns the entity for further mutation)

- [x] Task 3: Refactor `Scheduler._recover_checkpoints()` (AC: #1, #4)
  - [x] 3.1: Replace `session.execute(select(SpawnCheckpoint))` + `scalars().all()` at lines 214-215 with `spawn_repo.get_all_checkpoints(session)`

- [x] Task 4: Clean up imports in `scheduler.py` (AC: #4)
  - [x] 4.1: Remove `from sqlalchemy import select` (no longer needed — verify no other select usage)
  - [x] 4.2: Remove `from server.room.spawn_models import SpawnCheckpoint` (accessed only via repo now)
  - [x] 4.3: Add `from server.room import spawn_repo`

- [x] Task 5: Verify all tests pass (AC: #3)
  - [x] 5.1: Run `make test` — all 808 tests pass, 0 failures, 0 warnings
  - [x] 5.2: Existing tests in `tests/test_spawn.py` mock `session.execute` directly — mocks intercept at the SQLAlchemy level, all tests pass without changes

## Dev Notes

### Repo Pattern Reference

All existing repos follow this exact pattern (see `server/player/repo.py`, `server/room/repo.py`):
- Module-level async functions (NOT classes)
- First parameter: `session: AsyncSession`
- NO `session.commit()` calls — `Game.transaction()` context manager handles commit/rollback
- Use `session.flush()` after `session.add()` when caller needs the object back (for auto-increment IDs or continued mutation)
- `from __future__ import annotations` as first import

### Scheduler Code to Replace

**In `_run_rare_spawn_checks()` (lines 146-161):**
```python
# Current inline query (lines 146-152):
result = await session.execute(
    select(SpawnCheckpoint).where(
        SpawnCheckpoint.npc_key == npc_key,
        SpawnCheckpoint.room_key == room_key,
    )
)
cp = result.scalar_one_or_none()

# Current inline create (lines 153-161, if cp is None block):
if cp is None:
    cp = SpawnCheckpoint(
        npc_key=npc_key,
        room_key=room_key,
        next_check_at=now,
        currently_spawned=False,
    )
    session.add(cp)
    await session.flush()
```

Replace both blocks with a single upsert call that returns existing or creates new:
```python
cp = await spawn_repo.upsert_checkpoint(session, room_key, npc_key, next_check_at=now, currently_spawned=False)
```
The `**kwargs` (next_check_at, currently_spawned) are only applied when creating a new checkpoint. If an existing one is found, it is returned as-is for the caller to mutate.

**In `_recover_checkpoints()` (lines 214-215):**
```python
# Current inline query:
result = await session.execute(select(SpawnCheckpoint))
checkpoints = result.scalars().all()
```

Replace with:
```python
checkpoints = await spawn_repo.get_all_checkpoints(session)
```

### Test Impact Analysis

Tests in `tests/test_spawn.py` mock `session.execute` at the SQLAlchemy level. Since the repo functions internally call `session.execute`, the mocks will still intercept the calls. The tests should pass without changes.

Key test patterns:
- `TestRareSpawnChecks.test_rare_spawn_success` (line 171): mocks `session.execute` to return a `MagicMock` checkpoint
- `TestRareSpawnChecks.test_rare_spawn_roll_fails` (line 210): same pattern
- `TestCheckpointRecovery.test_recover_checkpoints_logs_overdue` (line 358): mocks `session.execute` for `scalars().all()`

If any test fails because the repo adds an extra `session.execute` call, patch at the repo function level: `patch("server.core.scheduler.spawn_repo.get_checkpoint", new_callable=AsyncMock)`

### File Placement

`spawn_repo.py` goes in `server/room/` because:
- `SpawnCheckpoint` model is in `server/room/spawn_models.py` — repo stays with its model
- `scheduler.py` already imports from `server/room/` (npc templates, spawn models) — no new cross-package dependency

### Anti-Patterns to Avoid

- Do NOT change any gameplay behavior — pure refactor
- Do NOT change assertion values in any existing test
- Do NOT add `session.commit()` in repo functions — transaction manager handles it
- Do NOT create a class-based repo — use module-level functions like all other repos
- Do NOT unify upsert patterns across repos (ADR-15-8: premature abstraction)
- All modified files MUST have `from __future__ import annotations` as the first import
- Use `make test` to run tests, never bare `pytest`

### Project Structure Notes

- `server/room/spawn_repo.py` — NEW: SpawnCheckpoint data access functions
- `server/room/spawn_models.py` — EXISTING: SpawnCheckpoint SQLAlchemy model (no changes needed)
- `server/core/scheduler.py` — MODIFY: replace inline queries with spawn_repo calls, clean up imports
- `tests/test_spawn.py` — VERIFY: existing tests should pass without changes

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Story 15.7 (lines 3882-3907)]
- [Source: server/core/scheduler.py — _run_rare_spawn_checks() (lines 126-204), _recover_checkpoints() (lines 210-224)]
- [Source: server/room/spawn_models.py — SpawnCheckpoint model (lines 10-18)]
- [Source: server/player/repo.py — repo pattern reference (module-level async functions)]
- [Source: server/room/repo.py — repo pattern reference (get_by_key, upsert_room)]
- [Source: tests/test_spawn.py — existing scheduler tests (mock session.execute pattern)]
- [Source: _bmad-output/implementation-artifacts/15-6-eventbus-resilience-config-gaps.md — previous story]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- All 808 tests pass (0 failures, 0 warnings, ~3.8s)

### Completion Notes List

- Created `server/room/spawn_repo.py` with three functions (`get_checkpoint`, `upsert_checkpoint`, `get_all_checkpoints`) following the project's module-level async function repo pattern
- Replaced inline `select(SpawnCheckpoint)` queries in `Scheduler._run_rare_spawn_checks()` with `spawn_repo.upsert_checkpoint()` call
- Replaced inline `select(SpawnCheckpoint)` query in `Scheduler._recover_checkpoints()` with `spawn_repo.get_all_checkpoints()` call
- Removed `from sqlalchemy import select` and `from server.room.spawn_models import SpawnCheckpoint` imports from `scheduler.py`
- Added `from server.room import spawn_repo` import to `scheduler.py`
- Zero gameplay behavior changes — pure refactor
- All existing 808 tests pass without modification

### File List

**New:**
- `server/room/spawn_repo.py` — SpawnCheckpoint data access functions (get_checkpoint, upsert_checkpoint, get_all_checkpoints)

**Modified:**
- `server/core/scheduler.py` — Replaced inline SpawnCheckpoint queries with spawn_repo calls, cleaned up imports
