# Story 9.3: Server Restart Mechanism

Status: done

## Story

As a server operator,
I want to trigger a graceful server restart via an authenticated REST endpoint,
so that I can apply updates or recover from issues without manual process management.

## Acceptance Criteria

1. **Given** the admin is authenticated (valid ADMIN_SECRET),
   **When** `POST /admin/restart` is called,
   **Then** the server responds with `{"status": "restarting"}` immediately.

2. **Given** restart has been triggered,
   **When** the restart process runs,
   **Then** `Game.shutdown()` is called first (saves all states, notifies clients, closes WebSockets),
   **And** the server process re-executes itself (same Python interpreter, same arguments),
   **And** the new process completes startup (init_db, load rooms/cards/items, start scheduler).

3. **Given** players were connected before restart,
   **When** the server comes back up,
   **Then** players can reconnect and login to find their saved state (position, stats, inventory) intact.

4. **Given** the restart re-execution fails (e.g., syntax error in updated code),
   **When** the new process cannot start,
   **Then** the failure is visible in the process output (no silent failure),
   **And** the old process has already exited (no zombie process).

5. **Given** a shutdown or restart is already in progress,
   **When** a restart request arrives,
   **Then** it is rejected with `{"status": "already_shutting_down"}`.

6. **And** all existing tests pass after implementation.

## Tasks / Subtasks

- [x] Task 1: Add POST /admin/restart endpoint (AC: 1, 5)
  - [x] In `server/net/handlers/admin.py`: add `POST /admin/restart` endpoint protected by `verify_admin_secret`
  - [x] Check `game._shutting_down` — if True, return `{"status": "already_shutting_down"}` with 409
  - [x] Set `game._shutting_down = True`
  - [x] Return `{"status": "restarting"}` immediately (200)
  - [x] Schedule restart in background task: `asyncio.create_task(_do_restart())`

- [x] Task 2: Implement restart background task (AC: 2, 3, 4)
  - [x] In `server/net/handlers/admin.py`: create `async def _do_restart()` helper
  - [x] Call `await game.shutdown()` first (saves all player states)
  - [x] After shutdown, re-execute the process using `os.execv(sys.executable, [sys.executable] + sys.argv)`
  - [x] `os.execv()` replaces current process — no zombie (AC 4)

- [x] Task 3: Write tests (AC: 1-6)
  - [x] In `tests/test_admin.py`: added 5 restart endpoint tests
  - [x] Test: POST /admin/restart with valid secret → 200 + `{"status": "restarting"}`
  - [x] Test: POST /admin/restart when already shutting down → 409 + `{"status": "already_shutting_down"}`
  - [x] Test: POST /admin/restart without auth → 403
  - [x] Test: verify `game.shutdown()` called then `os.execv` called with correct args
  - [x] Test: verify `_shutting_down` flag is set
  - [x] Existing tests still pass — 389 passed

## Dev Notes

### Previous Story Intelligence (9-1, 9-2)

- `verify_admin_secret` dependency, `admin_router`, `_shutting_down` flag all exist
- `_do_shutdown()` pattern from 9-2 — restart follows identical pattern
- Deferred import `from server.app import game` inside functions

### Key Implementation Details

- `os.execv(sys.executable, [sys.executable] + sys.argv)` replaces current process entirely
- `os.execv()` does NOT return on success — old process is gone
- Player state saved by `Game.shutdown()` before `execv`

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 9.3]
- [Source: server/net/handlers/admin.py — existing admin router and shutdown pattern]
- [Source: _bmad-output/implementation-artifacts/9-2-admin-shutdown-command.md]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Added `POST /admin/restart` endpoint with same `_shutting_down` guard as shutdown
- Background task `_do_restart()` calls `game.shutdown()` then `os.execv()` for process replacement
- 5 new restart tests — all pass
- 389 total tests pass (0 regressions)

### File List

- server/net/handlers/admin.py (modified — added restart endpoint + _do_restart task)
- tests/test_admin.py (modified — added 5 restart tests)
