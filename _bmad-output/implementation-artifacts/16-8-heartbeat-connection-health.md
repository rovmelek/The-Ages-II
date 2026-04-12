# Story 16.8: Heartbeat / Connection Health

Status: done

## Story

As a **game server operator**,
I want the server to detect dead WebSocket connections via application-level ping/pong heartbeat,
So that stale sessions are cleaned up promptly and don't leave ghost players in rooms.

## Acceptance Criteria

1. **Given** a player has successfully logged in,
   **When** `HEARTBEAT_INTERVAL_SECONDS` (default 30) elapses,
   **Then** the server sends `{"type": "ping"}` to that player's WebSocket.

2. **Given** a client receives `{"type": "ping"}`,
   **When** the client responds with `{"action": "pong"}`,
   **Then** the server resets the heartbeat cycle (next ping in `HEARTBEAT_INTERVAL_SECONDS`).

3. **Given** the server sends a ping,
   **When** no pong is received within `HEARTBEAT_TIMEOUT_SECONDS` (default 10),
   **Then** the server closes the WebSocket (triggers `handle_disconnect` normally).

4. **Given** the `pong` action handler,
   **When** it is registered,
   **Then** it uses `@requires_auth` — unauthenticated stray pongs are rejected.

5. **Given** `handle_disconnect` is called (for any reason),
   **When** a heartbeat task exists for that entity,
   **Then** the heartbeat task is cancelled BEFORE any other cleanup.

6. **Given** `Game.shutdown()` is called,
   **When** heartbeat tasks exist,
   **Then** all heartbeat tasks are cancelled BEFORE session iteration.

7. **Given** the heartbeat system,
   **When** a player re-logs in (duplicate login kicks old session),
   **Then** the old heartbeat task is cancelled and a new one is started for the new WebSocket.

8. **Given** the web-demo client,
   **When** it receives a `{"type": "ping"}` message,
   **Then** it responds with `{"action": "pong"}`.

9. **Given** `HEARTBEAT_INTERVAL_SECONDS` and `HEARTBEAT_TIMEOUT_SECONDS`,
   **When** they exist in `Settings`,
   **Then** they are configurable (not hardcoded).

10. **Given** heartbeat tasks,
    **When** stored,
    **Then** they are in `Game._heartbeat_tasks: dict[str, asyncio.Task]` keyed by entity_id.

11. **Given** the heartbeat task starts AFTER successful login,
    **When** a WebSocket connects but hasn't logged in yet,
    **Then** no heartbeat runs — unauthenticated connections are not timed out.

12. **Given** all 986 existing tests,
    **When** Story 16.8 is implemented,
    **Then** all tests pass unchanged (tests don't use real heartbeat tasks).

## Tasks / Subtasks

- [x] Task 1: Add config settings (AC: #9)
  - [x] 1.1: Add `HEARTBEAT_INTERVAL_SECONDS: int = 30` to `Settings` in `server/core/config.py`
  - [x] 1.2: Add `HEARTBEAT_TIMEOUT_SECONDS: int = 10` to `Settings` in `server/core/config.py`

- [x] Task 2: Add `PongMessage` inbound schema + `PingMessage` outbound schema (AC: #4)
  - [x] 2.1: Add `PongMessage(InboundMessage)` with `action: str = "pong"` to `server/net/schemas.py`
  - [x] 2.2: Add `"pong": PongMessage` to `ACTION_SCHEMAS` dict in `server/net/schemas.py`
  - [x] 2.3: Add `PingMessage(BaseModel)` with `type: str = "ping"` to `server/net/outbound_schemas.py`

- [x] Task 3: Add `_heartbeat_tasks` to `Game` and heartbeat methods (AC: #1, #3, #10)
  - [x] 3.1: Add `self._heartbeat_tasks: dict[str, asyncio.Task] = {}` to `Game.__init__` (`server/app.py:37-52`)
  - [x] 3.2: Add `import asyncio` to `server/app.py` (if not already present)
  - [x] 3.3: Add `_start_heartbeat(self, entity_id: str)` method to `Game` — creates and stores the heartbeat asyncio.Task
  - [x] 3.4: Add `_cancel_heartbeat(self, entity_id: str)` method to `Game` — cancels and removes task from dict
  - [x] 3.5: The heartbeat task loop: `while True` → send `{"type": "ping"}` → wait for pong event (with `HEARTBEAT_TIMEOUT_SECONDS` timeout) → if timeout, close WebSocket → sleep `HEARTBEAT_INTERVAL_SECONDS`

- [x] Task 4: Add pong handler (AC: #2, #4)
  - [x] 4.1: Create `handle_pong` in `server/net/handlers/auth.py` (or a new heartbeat module) — `@requires_auth`, sets the pong event on the heartbeat task
  - [x] 4.2: Register `"pong"` action in `Game._register_handlers` (`server/app.py`)

- [x] Task 5: Integrate heartbeat with login (AC: #1, #11)
  - [x] 5.1: At end of `handle_login` (`server/net/handlers/auth.py`), call `game._start_heartbeat(entity_id)` after session setup
  - [x] 5.2: In `_kick_old_session`, cancel old heartbeat via `game._cancel_heartbeat(entity_id)` before cleanup (AC: #7)

- [x] Task 6: Integrate heartbeat with disconnect and shutdown (AC: #5, #6)
  - [x] 6.1: In `Game.handle_disconnect` (`server/app.py:355-361`), call `self._cancel_heartbeat(entity_id)` BEFORE `cleanup_session`
  - [x] 6.2: In `Game.shutdown` (`server/app.py:113-141`), cancel all heartbeat tasks BEFORE session iteration loop

- [x] Task 7: Update web-demo client (AC: #8)
  - [x] 7.1: In `web-demo/js/game.js`, add `ping` handler in `dispatchMessage()` handlers that sends `{"action": "pong"}`

- [x] Task 8: Write tests (AC: #1-#12)
  - [ ] 8.1: Test heartbeat task sends ping at interval
  - [ ] 8.2: Test pong response resets heartbeat cycle
  - [ ] 8.3: Test timeout closes WebSocket when no pong received
  - [ ] 8.4: Test `handle_disconnect` cancels heartbeat before cleanup
  - [ ] 8.5: Test `shutdown` cancels all heartbeat tasks
  - [ ] 8.6: Test duplicate login cancels old heartbeat, starts new one
  - [ ] 8.7: Test `pong` handler requires auth
  - [ ] 8.8: Run `make test` — all tests pass

## Dev Notes

### Heartbeat Task Pattern

Use `asyncio.Event` for pong synchronization. The heartbeat task loop:

```python
async def _heartbeat_loop(self, entity_id: str) -> None:
    pong_event = self._pong_events[entity_id]
    ws = self.connection_manager.get_websocket(entity_id)
    while True:
        await asyncio.sleep(settings.HEARTBEAT_INTERVAL_SECONDS)
        ws = self.connection_manager.get_websocket(entity_id)
        if ws is None:
            break
        try:
            await ws.send_json({"type": "ping"})
        except Exception:
            break
        pong_event.clear()
        try:
            await asyncio.wait_for(pong_event.wait(), timeout=settings.HEARTBEAT_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            # No pong received — close WebSocket (triggers handle_disconnect)
            try:
                await ws.close(code=1000)
            except Exception:
                pass
            break
```

### Pong Event Tracking

Store `asyncio.Event` objects alongside tasks: `self._pong_events: dict[str, asyncio.Event] = {}`. The pong handler sets the event:

```python
game._pong_events[entity_id].set()
```

### Pong Handler

Minimal handler — just sets the event. Place in `server/net/handlers/auth.py` alongside login/logout:

```python
@requires_auth
async def handle_pong(
    websocket: WebSocket, data: dict, *, game: Game,
    entity_id: str, player_info: PlayerSession,
) -> None:
    """Handle 'pong' — heartbeat response, no-op beyond event signal."""
    event = game._pong_events.get(entity_id)
    if event:
        event.set()
```

### Cancel Pattern

```python
def _cancel_heartbeat(self, entity_id: str) -> None:
    task = self._heartbeat_tasks.pop(entity_id, None)
    if task and not task.done():
        task.cancel()
    self._pong_events.pop(entity_id, None)
```

### Existing Tests Impact

Existing tests don't call `_start_heartbeat` directly — they test handlers via mocked game objects. The heartbeat task is spawned only in `handle_login` which is tested with mocked WebSockets. Since `_start_heartbeat` creates an `asyncio.Task`, tests that call `handle_login` with real async might spawn tasks. However, most login tests mock the game object, so `game._start_heartbeat` won't be called on a real `Game` instance.

For tests that DO use a real `Game` instance (integration tests), the heartbeat tasks should be harmless since they sleep for 30 seconds before doing anything, and tests complete in < 5 seconds. If any issues arise, mock `_start_heartbeat` in test fixtures.

### Timer Pattern Reference

Story 16.10a used `loop.call_later` for combat turn timeouts in `CombatInstance`. This story uses `asyncio.Task` + `asyncio.Event` instead (different pattern) because:
- Heartbeat is a continuous loop, not a one-shot timer
- `asyncio.Event` cleanly coordinates between the heartbeat task and the pong handler

### Project Structure Notes

- `server/core/config.py` — `Settings` class with all game config
- `server/app.py:37-52` — `Game.__init__` (add `_heartbeat_tasks`, `_pong_events`)
- `server/app.py:355-361` — `handle_disconnect` (add heartbeat cancel)
- `server/app.py:113-141` — `shutdown` (add heartbeat cancel-all)
- `server/app.py:143+` — `_register_handlers` (add pong)
- `server/net/handlers/auth.py` — `handle_login` (start heartbeat), `handle_pong` (set event)
- `server/net/schemas.py` — `PongMessage` + `ACTION_SCHEMAS` entry
- `server/net/outbound_schemas.py` — `PingMessage` documentation
- `web-demo/js/game.js` — `dispatchMessage` handlers (add ping)
- `tests/test_heartbeat.py` — New test file

### References

- [Source: _bmad-output/planning-artifacts/epic-16-tech-spec.md#Story-16.8] — Full spec
- [Source: server/app.py:37-52] — `Game.__init__`
- [Source: server/app.py:113-141] — `Game.shutdown`
- [Source: server/app.py:355-361] — `Game.handle_disconnect`
- [Source: server/net/handlers/auth.py] — `handle_login`, `_kick_old_session`
- [Source: server/core/config.py] — `Settings` class

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Completion Notes List

- Added `HEARTBEAT_INTERVAL_SECONDS: int = 30` and `HEARTBEAT_TIMEOUT_SECONDS: int = 10` to Settings
- Added `PongMessage` inbound schema + `PingMessage` outbound schema
- Added `_heartbeat_tasks` and `_pong_events` dicts to `Game.__init__`
- `_start_heartbeat` creates asyncio.Task running `_heartbeat_loop`, stores Event for pong coordination
- `_cancel_heartbeat` cancels task, removes from dicts
- `_heartbeat_loop`: sleep interval → send ping → wait_for pong event with timeout → close WS on timeout
- `handle_pong` with `@requires_auth` sets the pong event
- `handle_login` calls `game._start_heartbeat(entity_id)` after session setup
- `_kick_old_session` calls `game._cancel_heartbeat(entity_id)` before cleanup
- `handle_disconnect` cancels heartbeat BEFORE cleanup_session
- `shutdown` cancels all heartbeat tasks BEFORE session iteration
- Web-demo `ping` handler sends `{"action": "pong"}` via `sendAction`
- 16 new tests in `tests/test_heartbeat.py`, 1002 total passing

### File List

- `server/core/config.py` — Modified: added HEARTBEAT_INTERVAL_SECONDS, HEARTBEAT_TIMEOUT_SECONDS
- `server/app.py` — Modified: import asyncio, _heartbeat_tasks/_pong_events in __init__, _start_heartbeat, _cancel_heartbeat, _heartbeat_loop, heartbeat cancel in handle_disconnect and shutdown, pong handler registration
- `server/net/handlers/auth.py` — Modified: handle_pong handler, _start_heartbeat call in handle_login, _cancel_heartbeat in _kick_old_session
- `server/net/schemas.py` — Modified: PongMessage class, pong entry in ACTION_SCHEMAS
- `server/net/outbound_schemas.py` — Modified: PingMessage class
- `web-demo/js/game.js` — Modified: ping handler in dispatchMessage
- `tests/test_heartbeat.py` — New: 16 tests for heartbeat lifecycle, loop, pong handler
- `tests/test_inbound_schemas.py` — Modified: updated schema count and key assertions for pong
