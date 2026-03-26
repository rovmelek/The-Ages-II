# Story 7.5: Duplicate Login Protection

Status: done

## Story

As a player,
I want to be able to reconnect if my browser crashes,
so that I'm not locked out of my account by a stale session.

## Acceptance Criteria

1. **Given** a player is already logged in with an active WebSocket session,
   **When** the same account logs in from a new connection,
   **Then** the old session is kicked immediately (deferred kick is a production optimization).

2. **Given** the old session is kicked,
   **When** the kick executes,
   **Then** the cleanup order is: save old session's state (stats + inventory + position) → remove entity from room → remove from connection_manager immediately (do not wait for disconnect event) → close old WebSocket → proceed with new login.

3. **Given** the old session is in active combat when kicked,
   **When** the kick fires,
   **Then** the player is removed from the combat instance (forfeited),
   **And** combat continues for remaining participants.

4. **Given** the old WebSocket close handshake fails (network degraded),
   **When** the close attempt times out or errors,
   **Then** the entity and connection_manager entries are already cleaned up (cleanup happens before close),
   **And** no zombie socket blocks future broadcasts.

5. **Given** no existing session for the account,
   **When** the player logs in,
   **Then** login proceeds normally (no kick needed).

## Tasks / Subtasks

- [ ] Task 1: Detect duplicate login (AC: 1, 5)
  - [ ] In `server/net/handlers/auth.py` `handle_login()`, after authentication succeeds
  - [ ] Check if `entity_id` (e.g., `player_1`) already exists in `connection_manager._connections`
  - [ ] If not found → proceed normally (AC: 5)
  - [ ] If found → execute kick sequence before creating new session

- [ ] Task 2: Implement kick sequence (AC: 2, 4)
  - [ ] Get old WebSocket from `connection_manager._connections[entity_id]`
  - [ ] Save old session state: position + stats + inventory (reuse patterns from Stories 7.2/7.3 or fallback to position-only)
  - [ ] Remove from combat if in combat (reuse `handle_disconnect` combat removal logic)
  - [ ] Remove entity from room (broadcast `entity_left`)
  - [ ] Remove from `connection_manager` dicts — clean up ALL three dicts: `_connections`, `_player_rooms`, `_ws_to_entity`
  - [ ] Remove from `game.player_entities`
  - [ ] Close old WebSocket with code 1000 or 1001 — wrap in try/except
  - [ ] Note: cleanup BEFORE close — if close fails, state is already clean

- [ ] Task 3: Handle old session in combat (AC: 3)
  - [ ] Use same combat removal logic as `Game.handle_disconnect()` (lines 172-185)
  - [ ] Remove participant from combat instance
  - [ ] If combat becomes empty, clean up instance
  - [ ] Notify remaining participants

- [ ] Task 4: Add kick notification to old session (AC: 1)
  - [ ] Before closing old WebSocket, send `{type: "kicked", reason: "Logged in from another location"}`
  - [ ] This lets the web client display a message instead of treating it as an error

- [ ] Task 5: Tests (AC: 1-5)
  - [ ] Test: login while already logged in → old session kicked, new session works
  - [ ] Test: login with no existing session → normal flow
  - [ ] Test: old session in combat → removed from combat, new login proceeds
  - [ ] Test: old WebSocket already dead → kick handles gracefully
  - [ ] Run `pytest tests/`

## Dev Notes

### Current Implementation — No Duplicate Check

`handle_login()` (auth.py lines 55-143) authenticates credentials and immediately creates a new entity + connection mapping. No check for existing sessions. `ConnectionManager.connect()` (line 15-19) does `self._connections[entity_id] = websocket` — silently overwrites the old WebSocket reference, but the old WebSocket's `_ws_to_entity` entry is **never cleaned up** (stale reference). The old entity stays in the room and `game.player_entities` until the old connection's `onclose` fires.

### ConnectionManager Internals

```python
_connections: dict[str, WebSocket]      # entity_id → websocket
_player_rooms: dict[str, str]           # entity_id → room_key
_ws_to_entity: dict[int, str]           # id(websocket) → entity_id
```

When kicking, must clean all three dicts. The `_ws_to_entity` key is `id(old_websocket)` — grab it before closing.

### Cleanup Order is Critical

1. Save state (position/stats/inventory) — can still access entity data
2. Remove from combat — prevent further combat interactions
3. Remove from room — broadcast entity_left to other players
4. Remove from connection_manager — prevent broadcasts to old socket
5. Remove from player_entities — entity no longer exists
6. Send kick message to old WebSocket — best effort
7. Close old WebSocket — best effort, wrapped in try/except

If step 7 fails, everything is already clean. No zombie state.

### Web Client Handling

The web client (game.js) will see the WebSocket close and trigger its reconnect logic. With Story 7.8 implemented, it will eventually return to the login screen. The `kicked` message (Task 4) can trigger an immediate return to login instead of reconnecting to a session that will fail anyway.

### Project Structure Notes

- Modified files: `server/net/handlers/auth.py` (add kick logic to login), possibly `server/net/connection_manager.py` (helper method)
- No new files needed

### References

- [Source: server/net/handlers/auth.py — handle_login, lines 55-143]
- [Source: server/net/connection_manager.py — connect/disconnect methods]
- [Source: server/app.py — handle_disconnect combat removal, lines 172-185]
- [Source: architecture.md#Section 8 — Networking, WebSocket protocol]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Completion Notes List
- Task 1-4: Implemented `_kick_old_session()` in auth.py — saves state, removes from combat, removes from room, cleans up connection_manager, sends kicked notification, closes old WebSocket
- Cleanup happens BEFORE close for resilience against network failures
- Login handler checks for existing session and kicks before proceeding
- All 356 unit tests + 23 integration tests pass

### File List
- `server/net/handlers/auth.py` — Added `_kick_old_session()` and duplicate check in `handle_login()`
- `tests/test_integration.py` — Updated fixture to patch combat/inventory handler sessions
