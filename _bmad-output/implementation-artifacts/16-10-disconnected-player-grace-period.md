# Story 16.10: Disconnected Player Grace Period

Status: done

## Story

As a **player who briefly backgrounds the app to check a text message**,
I want my combat, party, and room position preserved for 2 minutes,
So that I don't lose my game state from a brief interruption.

## Acceptance Criteria

1. **Given** a player's WebSocket connection drops,
   **When** `handle_disconnect` runs,
   **Then** the WebSocket mapping is removed, `session.disconnected_at` set to `time.time()`, `entity.connected` set to `False`,
   **And** trades ARE cancelled immediately (can't block other player),
   **And** combat, party, and room presence are NOT cleaned up,
   **And** a deferred cleanup timer is scheduled for `DISCONNECT_GRACE_SECONDS` (default 120),
   **And** the timer handle is stored in `Game._cleanup_handles[entity_id]`.

2. **Given** an existing deferred cleanup timer for the same entity,
   **When** `handle_disconnect` runs again (disconnect->reconnect->disconnect),
   **Then** the old timer is cancelled before the new one is stored (defensive idempotency).

3. **Given** the server is shutting down (`self._shutting_down is True`),
   **When** `handle_disconnect` runs,
   **Then** it returns early — no deferred timer scheduled (shutdown handles all cleanup).

4. **Given** the grace period expires without reconnection,
   **When** the deferred cleanup timer fires,
   **Then** `player_manager.deferred_cleanup(entity_id, game)` runs (PUBLIC method),
   **And** combat, party, room, and DB state are fully cleaned up.

5. **Given** a player reconnects within the grace period (via Story 16.9 Case 1),
   **When** the reconnect handler runs,
   **Then** the deferred cleanup timer is cancelled, `disconnected_at` cleared, `entity.connected` restored to `True`.

6. **Given** a player logs in from another device during grace period (via `handle_login`, not reconnect),
   **When** `handle_login` detects a grace-period session (`player_manager.has_session(entity_id)` and no WebSocket),
   **Then** it cancels the deferred cleanup timer, runs full cleanup, then creates new session,
   **And** combat/party state from the old session is properly cleaned up (no dangling references).

7. **Given** `room_state` entity data during grace period,
   **When** other players request room state,
   **Then** the disconnected entity includes `connected: false` (read from `PlayerEntity.connected` field via `getattr`).

8. **Given** `Game.shutdown()` runs,
   **When** cleanup handles exist,
   **Then** all pending deferred timers are cancelled before session iteration.

9. **Given** `DISCONNECT_GRACE_SECONDS` (default 120),
   **When** it exists in `Settings`,
   **Then** it is configurable (not hardcoded).

10. **Given** the test suite,
    **When** Story 16.10 is implemented,
    **Then** an `autouse` fixture in `tests/conftest.py` sets `DISCONNECT_GRACE_SECONDS=0`,
    **And** all existing tests pass via the fixture (immediate cleanup preserved),
    **And** new grace-period tests use non-zero values.

11. **Given** `PlayerManager.deferred_cleanup()`,
    **When** it exists,
    **Then** it is a PUBLIC method — `Game._deferred_cleanup` does NOT call private `PlayerManager` methods directly.

## Tasks / Subtasks

- [x] Task 1: Add `autouse` fixture for `DISCONNECT_GRACE_SECONDS=0` (AC: #10) — **FIRST before any code changes**
  - [x] 1.1: Add `DISCONNECT_GRACE_SECONDS` autouse session-scoped fixture to `tests/conftest.py` that monkeypatches `settings.DISCONNECT_GRACE_SECONDS = 0`
  - [x] 1.2: Run `make test` — all 1031 existing tests pass (confirms fixture doesn't break anything)

- [x] Task 2: Add config setting (AC: #9)
  - [x] 2.1: Add `DISCONNECT_GRACE_SECONDS: int = 120` to `Settings` in `server/core/config.py` (after `SESSION_TOKEN_TTL_SECONDS` line 84)

- [x] Task 3: Add `PlayerManager.deferred_cleanup()` public method (AC: #4, #11)
  - [x] 3.1: Add `deferred_cleanup(entity_id, game)` to `PlayerManager` (`server/player/manager.py`) — skips trade cleanup and WS disconnect (already done in `handle_disconnect`), calls `_cleanup_combat`, `_cleanup_party`, `_save_player_state`, `_remove_from_room`, then `remove_session`

- [x] Task 4: Add `_deferred_cleanup` method to `Game` (AC: #4)
  - [x] 4.1: Add `_deferred_cleanup(self, entity_id)` to `Game` (`server/app.py`) — pops cleanup handle, checks session exists and `disconnected_at` is not None, calls `self.player_manager.deferred_cleanup(entity_id, self)`

- [x] Task 5: Modify `handle_disconnect` for deferred cleanup (AC: #1, #2, #3)
  - [x] 5.1: Add `import time` to `server/app.py` if not present
  - [x] 5.2: Rewrite `handle_disconnect` to: check `_shutting_down` (return early), cancel heartbeat, get session (if None disconnect and return), disconnect WebSocket mapping, set `disconnected_at` and `entity.connected = False`, cancel trades immediately, cancel any existing timer for entity, schedule deferred cleanup via `loop.call_later`
  - [x] 5.3: If `DISCONNECT_GRACE_SECONDS == 0`, run immediate cleanup instead of scheduling a timer (preserves existing behavior for tests using the autouse fixture)

- [x] Task 6: Modify `shutdown` to cancel all deferred timers (AC: #8)
  - [x] 6.1: In `Game.shutdown()` (`server/app.py:119-151`), cancel all `_cleanup_handles` timers and clear the dict before heartbeat cancellation

- [x] Task 7: Modify `handle_login` for grace-period detection (AC: #6)
  - [x] 7.1: In `handle_login` (`server/net/handlers/auth.py:239-296`), after `entity_id = f"player_{player.id}"` (line 248), check `player_manager.has_session(entity_id)` AND `connection_manager.get_websocket(entity_id) is None`. If both true: cancel cleanup handle, cancel heartbeat, run `cleanup_session`, then proceed with normal login

- [x] Task 8: Modify `get_state()` to include `connected` field (AC: #7)
  - [x] 8.1: In `RoomInstance.get_state()` (`server/room/room.py:185-203`), add `"connected": getattr(e, "connected", True)` to the entity dict

- [x] Task 9: Update outbound schema for `connected` field (AC: #7)
  - [x] 9.1: Add `connected: bool | None = None` to `EntityPayload` in `server/net/outbound_schemas.py` (lines 42-51)

- [x] Task 10: Write tests (AC: #1-#11)
  - [x] 10.1: Test `handle_disconnect` with `DISCONNECT_GRACE_SECONDS > 0` schedules deferred cleanup, keeps session alive
  - [x] 10.2: Test deferred cleanup fires after grace period — session removed, combat/party/room cleaned up
  - [x] 10.3: Test `handle_disconnect` during shutdown returns early (no timer scheduled)
  - [x] 10.4: Test `handle_disconnect` cancels existing timer (idempotent)
  - [x] 10.5: Test `handle_login` during grace period — cancels timer, cleans up old session
  - [x] 10.6: Test `get_state()` includes `connected: false` for disconnected entity
  - [x] 10.7: Test `shutdown` cancels all cleanup handles
  - [x] 10.8: Test `DISCONNECT_GRACE_SECONDS == 0` runs immediate cleanup
  - [x] 10.9: Run `make test` — all tests pass

## Dev Notes

### Story 16.9 Already Added Stub Fields

Story 16.9 added the following as stubs — this story populates them:
- `disconnected_at: float | None = None` on `PlayerSession` (`server/player/session.py:21`)
- `connected: bool = True` on `PlayerEntity` (`server/player/entity.py:16`)
- `self._cleanup_handles: dict[str, asyncio.TimerHandle] = {}` on `Game.__init__` (`server/app.py:57`)

No new fields need to be created — only code that **sets** these fields.

### handle_disconnect Rewrite

Current `handle_disconnect` (`server/app.py:372-381`) immediately calls `cleanup_session`. The rewrite:

```python
async def handle_disconnect(self, websocket: WebSocket) -> None:
    entity_id = self.connection_manager.get_entity_id(websocket)
    if entity_id is None:
        return

    # During shutdown, shutdown() handles all cleanup
    if self._shutting_down:
        return

    self._cancel_heartbeat(entity_id)

    session = self.player_manager.get_session(entity_id)
    if session is None:
        self.connection_manager.disconnect(entity_id)
        return

    # Disconnect WebSocket mapping but keep session alive
    self.connection_manager.disconnect(entity_id)

    # Mark as disconnected
    session.disconnected_at = time.time()
    session.entity.connected = False

    # Cancel trades immediately (can't block other players)
    await self.player_manager._cleanup_trade(entity_id, self)

    # Cancel any existing deferred timer (defensive idempotency)
    old_handle = self._cleanup_handles.pop(entity_id, None)
    if old_handle is not None:
        old_handle.cancel()

    # Immediate cleanup if grace period is 0 (test mode)
    if settings.DISCONNECT_GRACE_SECONDS <= 0:
        await self.player_manager.deferred_cleanup(entity_id, self)
        return

    # Schedule deferred full cleanup
    loop = asyncio.get_running_loop()
    def _on_grace_expired():
        loop.create_task(self._deferred_cleanup(entity_id))
    handle = loop.call_later(settings.DISCONNECT_GRACE_SECONDS, _on_grace_expired)
    self._cleanup_handles[entity_id] = handle
```

**Key design choice**: When `DISCONNECT_GRACE_SECONDS == 0`, call `deferred_cleanup` immediately instead of scheduling a timer. This preserves existing test behavior via the `autouse` fixture without requiring all existing tests to run an event loop tick.

### PlayerManager.deferred_cleanup()

New PUBLIC method on `PlayerManager` (`server/player/manager.py`):

```python
async def deferred_cleanup(self, entity_id: str, game: Game) -> None:
    """Deferred cleanup after grace period — skips trade + WS disconnect."""
    session = self.get_session(entity_id)
    if session is None:
        return
    entity = session.entity
    room_key = session.room_key
    await self._cleanup_combat(entity_id, entity, game)
    await self._cleanup_party(entity_id, game)
    await self._save_player_state(entity_id, session, game)
    await self._remove_from_room(entity_id, room_key, game)
    self.remove_session(entity_id)
```

Differs from `cleanup_session` in two ways:
1. Skips `_cleanup_trade` (already done in `handle_disconnect`)
2. Skips `connection_manager.disconnect` (already done in `handle_disconnect`)

### handle_login Grace-Period Detection

In `handle_login` (`server/net/handlers/auth.py:248-255`), after `entity_id = f"player_{player.id}"`, add check:

```python
# Check for grace-period session (WS gone, session still alive)
existing_session = game.player_manager.get_session(entity_id)
if existing_session is not None and game.connection_manager.get_websocket(entity_id) is None:
    cleanup_handle = game._cleanup_handles.pop(entity_id, None)
    if cleanup_handle is not None:
        cleanup_handle.cancel()
    game._cancel_heartbeat(entity_id)
    await game.player_manager.cleanup_session(entity_id, game)
```

This is added BEFORE the existing `old_ws = game.connection_manager.get_websocket(entity_id)` check at line 250 — do NOT replace it. The existing check handles active-WebSocket duplicate logins (player logged in from another device with WS still open). The new check handles grace-period sessions (WS gone, session alive in memory). Both checks must coexist.

### RoomInstance.get_state() Change

Add `"connected": getattr(e, "connected", True)` to entity dict in `get_state()` (`server/room/room.py:187-190`). Uses `getattr` with default `True` for backward compatibility.

### Name Mapping Removal During Grace Period

`ConnectionManager.disconnect(entity_id)` removes `_name_to_entity` and `_entity_to_name` mappings. During the grace period, the player's entity remains in the room but cannot be found by name (whisper, trade invite, party invite will fail). This is **intentional** — a disconnected player should not receive new interactions. On reconnect, `connection_manager.connect()` restores the name mapping.

### Reconnect Integration (Story 16.9)

Story 16.9's `handle_reconnect` Case 1 already handles:
- Cancelling `_cleanup_handles[entity_id]`
- Clearing `disconnected_at`
- Setting `entity.connected = True`
- Re-registering WebSocket

No changes needed to `handle_reconnect` for this story.

### Test Strategy

**Critical first step**: Add `autouse` fixture setting `DISCONNECT_GRACE_SECONDS=0` before ANY code changes. This ensures all 1031 existing tests continue using immediate cleanup behavior.

New tests use `monkeypatch` to set `DISCONNECT_GRACE_SECONDS` to non-zero values for grace period scenarios.

### Files to Modify

| File | Change |
|------|--------|
| `tests/conftest.py` | Add `autouse` fixture: `DISCONNECT_GRACE_SECONDS=0` |
| `server/core/config.py` | Add `DISCONNECT_GRACE_SECONDS: int = 120` after line 84 |
| `server/player/manager.py` | Add public `deferred_cleanup()` method |
| `server/app.py:372-381` | Rewrite `handle_disconnect` for deferred cleanup |
| `server/app.py` | Add `_deferred_cleanup` method, add `import time` |
| `server/app.py:119-151` | `shutdown()` cancels all cleanup handles before session iteration |
| `server/net/handlers/auth.py:248-255` | `handle_login` grace-period detection |
| `server/room/room.py:187-190` | `get_state()` adds `connected` field to entity dict |
| `server/net/outbound_schemas.py:42-51` | `EntityPayload` adds `connected` field |
| `tests/test_grace_period.py` | **New** — grace period tests |

### Key Patterns

- **`loop.call_later` + `loop.create_task`**: Same pattern as `TradeManager._handle_timeout` (`server/trade/manager.py`)
- **`_cleanup_trade` called directly**: `PlayerManager._cleanup_trade` is private but called from `Game.handle_disconnect` — this matches the tech spec design where trades are cleaned immediately
- **No changes to `handle_reconnect`**: Story 16.9 already implements the reconnect-side of grace period

### References

- [Source: epic-16-tech-spec.md#Story-16.10] — Full spec (lines 1283-1529)
- [Source: epics.md#Story-16.10] — BDD acceptance criteria (lines 4474-4535)
- [Source: server/app.py:372-381] — Current `handle_disconnect` (to be rewritten)
- [Source: server/app.py:119-151] — `shutdown()` (add timer cancellation)
- [Source: server/app.py:57] — `_cleanup_handles` stub (from 16.9)
- [Source: server/player/session.py:21] — `disconnected_at` stub (from 16.9)
- [Source: server/player/entity.py:16] — `connected` stub (from 16.9)
- [Source: server/player/manager.py:55-78] — `cleanup_session` (model for `deferred_cleanup`)
- [Source: server/room/room.py:185-203] — `get_state()` entity serialization
- [Source: server/net/handlers/auth.py:248-255] — `handle_login` existing session check

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Completion Notes List

- Added `autouse` session-scoped fixture `_zero_grace_period` to `tests/conftest.py` — sets `DISCONNECT_GRACE_SECONDS=0` for all existing tests
- Added `DISCONNECT_GRACE_SECONDS: int = 120` to Settings
- Added `PlayerManager.deferred_cleanup()` public method — skips trade + WS disconnect (already done in handle_disconnect)
- Added `Game._deferred_cleanup()` — pops handle, checks session still disconnected, delegates to `player_manager.deferred_cleanup`
- Rewrote `handle_disconnect` for deferred cleanup: `_shutting_down` check, cancel heartbeat, disconnect WS mapping, mark `disconnected_at`/`connected`, cancel trades immediately, schedule deferred cleanup via `loop.call_later` (or immediate if `DISCONNECT_GRACE_SECONDS=0`)
- Modified `shutdown()` — cancels all `_cleanup_handles` timers before session iteration
- Modified `handle_login` — detects grace-period sessions (has_session + no WS), cancels timer, cleans up before new session creation
- Modified `RoomInstance.get_state()` — entity dict includes `"connected": getattr(e, "connected", True)`
- Added `connected: bool | None = None` to `EntityPayload` outbound schema
- Fixed heartbeat tests using `Game.__new__` to include `_shutting_down`, `_cleanup_handles` attrs
- 14 new tests in `test_grace_period.py`, 1045 total passing

### File List

- `tests/conftest.py` — Modified: added `_zero_grace_period` autouse fixture
- `server/core/config.py` — Modified: added `DISCONNECT_GRACE_SECONDS`
- `server/player/manager.py` — Modified: added public `deferred_cleanup()` method
- `server/app.py` — Modified: import time, `_deferred_cleanup` method, rewritten `handle_disconnect`, shutdown timer cancellation
- `server/net/handlers/auth.py` — Modified: `handle_login` grace-period detection
- `server/room/room.py` — Modified: `get_state()` includes `connected` field
- `server/net/outbound_schemas.py` — Modified: `EntityPayload` adds `connected` field
- `tests/test_heartbeat.py` — Modified: updated `Game.__new__` tests with new attrs
- `tests/test_grace_period.py` — **New**: 14 grace period tests
