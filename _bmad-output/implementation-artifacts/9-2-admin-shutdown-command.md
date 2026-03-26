# Story 9.2: Admin Shutdown Command

Status: done

## Story

As a server operator,
I want to trigger a graceful server shutdown via an authenticated REST endpoint,
so that I can shut down the server remotely without killing the process.

## Acceptance Criteria

1. **Given** the admin is authenticated (valid ADMIN_SECRET),
   **When** `POST /admin/shutdown` is called,
   **Then** the server responds with `{"status": "shutting_down"}` immediately.

2. **Given** shutdown has been triggered,
   **When** the shutdown process runs,
   **Then** `Game.shutdown()` is called (saves all player states, notifies clients, closes WebSockets),
   **And** the uvicorn server process exits cleanly after shutdown completes.

3. **Given** a shutdown is already in progress,
   **When** another shutdown request arrives,
   **Then** it is rejected with `{"status": "already_shutting_down"}`.

4. **Given** players are connected when shutdown is triggered,
   **When** the shutdown completes,
   **Then** all players have received `server_shutdown` message,
   **And** all player states (position, stats, inventory) are saved to DB,
   **And** all WebSocket connections are closed with code 1001.

5. **And** all existing tests pass after implementation.

## Tasks / Subtasks

- [x] Task 1: Add shutdown state tracking to Game (AC: 3)
  - [x] In `server/app.py` `Game.__init__`: add `self._shutting_down: bool = False`
  - [x] This flag prevents duplicate shutdown requests

- [x] Task 2: Add POST /admin/shutdown endpoint (AC: 1, 2, 3)
  - [x] In `server/net/handlers/admin.py`: add `POST /admin/shutdown` endpoint protected by `verify_admin_secret`
  - [x] Check `game._shutting_down` — if True, return `{"status": "already_shutting_down"}` with 409 Conflict
  - [x] Set `game._shutting_down = True`
  - [x] Return `{"status": "shutting_down"}` immediately (200)
  - [x] Schedule actual shutdown in a background task: `asyncio.create_task(_do_shutdown())`
  - [x] The background task calls `await game.shutdown()` then sends SIGTERM to self to stop uvicorn

- [x] Task 3: Implement shutdown background task (AC: 2, 4)
  - [x] In `server/net/handlers/admin.py`: create `async def _do_shutdown()` helper
  - [x] Call `await game.shutdown()` — handles save all player states, notify clients, close WebSockets with code 1001
  - [x] After shutdown completes, send `os.kill(os.getpid(), signal.SIGTERM)` to trigger uvicorn graceful exit

- [x] Task 4: Wire game reference to admin endpoints (AC: 1, 2)
  - [x] Deferred import `from server.app import game` inside endpoint and background task functions to avoid circular imports

- [x] Task 5: Write tests (AC: 1-5)
  - [x] In `tests/test_admin.py`: added 5 shutdown endpoint tests
  - [x] Test: POST /admin/shutdown with valid secret → 200 + `{"status": "shutting_down"}`
  - [x] Test: POST /admin/shutdown when already shutting down → 409 + `{"status": "already_shutting_down"}`
  - [x] Test: POST /admin/shutdown without auth → 403
  - [x] Test: verify `game.shutdown()` is called during shutdown
  - [x] Test: verify `_shutting_down` flag is set
  - [x] Existing tests still pass — 384 passed

## Dev Notes

### Previous Story Intelligence (9-1)

- Admin auth is implemented in `server/net/handlers/admin.py` with `verify_admin_secret` dependency and `admin_router`
- Router is included in `server/app.py` via `app.include_router(admin_router)`
- Auth uses `Authorization: Bearer <secret>` header with `hmac.compare_digest()`
- Tests use `httpx.ASGITransport` + `AsyncClient` with `monkeypatch` for setting ADMIN_SECRET
- **Reuse**: `verify_admin_secret` dependency, `admin_router`, test fixtures `_set_admin_secret` and `_clear_admin_secret`

### Key Implementation Details

- `Game.shutdown()` already exists and handles all player state saving, client notification, and WebSocket closure
- The endpoint returns immediately, then runs shutdown asynchronously via `asyncio.create_task()`
- To stop uvicorn after shutdown, use `os.kill(os.getpid(), signal.SIGTERM)`
- Deferred import `from server.app import game` inside endpoint functions to avoid circular imports

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 9.2]
- [Source: server/app.py:81-134 — existing Game.shutdown() method]
- [Source: server/net/handlers/admin.py — admin router]
- [Source: _bmad-output/implementation-artifacts/9-1-admin-authentication.md]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Added `self._shutting_down: bool = False` to `Game.__init__` in `server/app.py`
- Added `POST /admin/shutdown` endpoint with duplicate-request guard (409 if already shutting down)
- Background task `_do_shutdown()` calls `game.shutdown()` then SIGTERM self
- Deferred import pattern for `game` singleton to avoid circular imports
- 5 new shutdown tests + 5 existing auth tests = 10 tests in test_admin.py, all pass
- 384 total tests pass (0 regressions)

### File List

- server/app.py (modified — added `_shutting_down` flag to Game.__init__)
- server/net/handlers/admin.py (modified — added shutdown endpoint + _do_shutdown background task)
- tests/test_admin.py (modified — added 5 shutdown tests + autouse reset fixture)
