# Story 16.11: Message Acknowledgment IDs

Status: done

## Story

As a **game engine client developer**,
I want critical server messages to include sequence numbers,
So that after reconnecting I can tell the server the last message I received and determine if I missed anything.

## Acceptance Criteria

1. **Given** the server sends a critical message (combat_turn, combat_end, trade_update, xp_gained, level_up_available),
   **When** `connection_manager.send_to_player_seq(entity_id, message)` is called,
   **Then** the message includes a `seq` field (integer, monotonically increasing per player).

2. **Given** a player connects for the first time,
   **When** `ConnectionManager.connect()` is called,
   **Then** `_msg_seq` is initialized to 0 via `setdefault` (preserves existing value on reconnect).

3. **Given** a player reconnects with `{"action": "reconnect", "session_token": "...", "last_seq": 42}`,
   **When** the server compares `last_seq` with `connection_manager.get_msg_seq(entity_id)`,
   **Then** if they match: the client is up to date (no extra resync needed); if they differ or `last_seq` is missing: full state resync sent (which already happens on reconnect).

4. **Given** a player disconnects during grace period,
   **When** the `_msg_seq` counter is checked,
   **Then** it persists (not removed by `disconnect()`) — only cleared by `clear_msg_seq` during full cleanup.

5. **Given** cosmetic messages (entity_moved, chat, entity_entered),
   **When** sent via broadcast,
   **Then** they do NOT include `seq` — only critical direct messages use sequence numbers.

6. **Given** `ConnectionManager`,
   **When** `send_to_player_seq` is added,
   **Then** `ConnectionManager` has NO new imports from player/combat/trade modules (per ADR-16-3).

7. **Given** `notify_xp` in `server/core/xp.py`,
   **When** Story 16.11 is implemented,
   **Then** it switches from `ws.send_json` to `connection_manager.send_to_player_seq` for `xp_gained` and `level_up_available`.

8. **Given** all existing tests,
   **When** Story 16.11 is implemented,
   **Then** all tests pass unchanged (`seq` field is additive).

9. **Given** a fresh login (not reconnect),
   **When** `cleanup_session` or `deferred_cleanup` runs,
   **Then** `clear_msg_seq(entity_id)` is called to reset the counter.

## Tasks / Subtasks

- [x] Task 1: Add `_msg_seq` tracking to `ConnectionManager` (AC: #1, #2, #4, #6)
  - [x] 1.1: Add `self._msg_seq: dict[str, int] = {}` to `ConnectionManager.__init__` (`server/net/connection_manager.py:11-16`)
  - [x] 1.2: Add `self._msg_seq.setdefault(entity_id, 0)` to `connect()` method (preserves value on reconnect)
  - [x] 1.3: Do NOT remove `_msg_seq` in `disconnect()` (grace period needs it)
  - [x] 1.4: Add `get_msg_seq(entity_id) -> int` method — returns `_msg_seq.get(entity_id, 0)`
  - [x] 1.5: Add `clear_msg_seq(entity_id)` method — `_msg_seq.pop(entity_id, None)`
  - [x] 1.6: Add `send_to_player_seq(entity_id, message)` async method — increments seq, creates copy with `msg = {**message, "seq": seq}` (do NOT mutate original — aliasing safety), sends via WebSocket with try/except guard

- [x] Task 2: Call `clear_msg_seq` in cleanup paths (AC: #9)
  - [x] 2.1: In `PlayerManager.cleanup_session` (`server/player/manager.py:55-78`), call `game.connection_manager.clear_msg_seq(entity_id)` before `remove_session`
  - [x] 2.2: In `PlayerManager.deferred_cleanup` (`server/player/manager.py:80-95`), call `game.connection_manager.clear_msg_seq(entity_id)` before `remove_session`

- [x] Task 3: Add `last_seq` to `ReconnectMessage` inbound schema (AC: #3)
  - [x] 3.1: Add `last_seq: int | None = None` to `ReconnectMessage` in `server/net/schemas.py`

- [x] Task 4: Modify `handle_reconnect` to check `last_seq` (AC: #3)
  - [x] 4.1: In both Case 1 and Case 2 of `handle_reconnect` (`server/net/handlers/auth.py:307-465`), after sending `login_success`, compare `data.get("last_seq")` with `game.connection_manager.get_msg_seq(entity_id)`. If they match, send `{"type": "seq_status", "status": "up_to_date"}`. The full resync (room_state, combat_state) is already sent in both cases.

- [x] Task 5: Switch critical message senders to `send_to_player_seq` (AC: #1, #5, #7)
  - [x] 5.1: `_broadcast_combat_state` in `server/net/handlers/combat.py:41-50` — change `ws.send_json` to `game.connection_manager.send_to_player_seq(eid, ...)`
  - [x] 5.2: `_send_combat_end_message` in `server/net/handlers/combat.py:53-70` — remove the `ws = ... / if not ws: return` early guard (lines 58-60) since `send_to_player_seq` handles absent WebSockets internally; build the `player_end_result` dict unconditionally; change `ws.send_json` to `game.connection_manager.send_to_player_seq(eid, ...)`
  - [x] 5.3: `notify_xp` in `server/core/xp.py:92-112` — change `ws.send_json` to `game.connection_manager.send_to_player_seq(entity_id, ...)`
  - [x] 5.4: `send_level_up_available` in `server/core/xp.py:151-185` — change `ws.send_json` to `game.connection_manager.send_to_player_seq(entity_id, ...)`
  - [x] 5.5: `_send_trade_update` in `server/net/handlers/trade.py:49-53` — change `send_to_player` to `send_to_player_seq` for `trade_update`

- [x] Task 6: Update outbound schemas for `seq` field (AC: #1)
  - [x] 6.1: Add `seq: int | None = None` to `CombatTurnMessage`, `CombatEndMessage`, `XpGainedMessage`, `LevelUpAvailableMessage`, `TradeUpdateMessage` in `server/net/outbound_schemas.py`
  - [x] 6.2: Add `SeqStatusMessage(BaseModel)` with `type: str = "seq_status"` and `status: str` to `server/net/outbound_schemas.py`

- [x] Task 7: Write tests (AC: #1-#9)
  - [x] 7.1: Unit test `send_to_player_seq` increments counter and attaches `seq`
  - [x] 7.2: Unit test `connect` initializes `_msg_seq` via `setdefault`
  - [x] 7.3: Unit test `disconnect` does NOT remove `_msg_seq`
  - [x] 7.4: Unit test `clear_msg_seq` removes counter
  - [x] 7.5: Unit test `get_msg_seq` returns 0 for unknown player
  - [x] 7.6: Test reconnect with `last_seq` matching — receives `seq_status: up_to_date`
  - [x] 7.7: Test reconnect without `last_seq` — no `seq_status` sent (full resync only)
  - [x] 7.8: Test `cleanup_session` calls `clear_msg_seq`
  - [x] 7.9: Run `make test` — all tests pass

## Dev Notes

### ConnectionManager Changes

Add to `server/net/connection_manager.py`:

```python
# In __init__:
self._msg_seq: dict[str, int] = {}  # entity_id -> outbound seq counter

# In connect():
self._msg_seq.setdefault(entity_id, 0)  # Preserve on reconnect, init on first

# NOT in disconnect() — grace period needs seq to persist

def get_msg_seq(self, entity_id: str) -> int:
    return self._msg_seq.get(entity_id, 0)

def clear_msg_seq(self, entity_id: str) -> None:
    self._msg_seq.pop(entity_id, None)

async def send_to_player_seq(self, entity_id: str, message: dict) -> None:
    seq = self._msg_seq.get(entity_id, 0) + 1
    self._msg_seq[entity_id] = seq
    msg = {**message, "seq": seq}  # Copy — don't mutate original (aliasing safety)
    ws = self._connections.get(entity_id)
    if ws:
        try:
            await ws.send_json(msg)
        except Exception:
            pass  # Dead connection — seq still incremented for consistency
```

**Error handling**: `send_to_player_seq` wraps `ws.send_json` in `try/except Exception: pass` — same pattern as existing `send_to_player` and `broadcast_to_room`. This means callers (notify_xp, send_level_up_available, combat handlers) can remove their own try/except guards when switching to `send_to_player_seq`.

**Important**: `send_to_player_seq` increments the counter even if the WebSocket is None (player disconnected during grace period). This ensures the counter stays consistent — when the player reconnects, `last_seq` will correctly identify missed messages.

**Critical**: `send_to_player_seq` must NOT mutate the original `message` dict in-place. The trade handler calls it twice with the same `msg` dict (once for player_a, once for player_b). If the dict is mutated in-place, player_b would receive player_a's seq. Use `msg = {**message, "seq": seq}` to create a copy with seq attached, rather than `message["seq"] = seq`.

### Gradual Adoption — Which Senders to Switch

Priority messages (switch to `send_to_player_seq`):

| Message | File | Current pattern |
|---------|------|-----------------|
| `combat_turn` | `server/net/handlers/combat.py:48-50` | `ws.send_json` per participant |
| `combat_end` | `server/net/handlers/combat.py:70` | `ws.send_json` |
| `trade_update` | `server/net/handlers/trade.py:52-53` | `send_to_player` |
| `xp_gained` | `server/core/xp.py:102-108` | `ws.send_json` |
| `level_up_available` | `server/core/xp.py:160-183` | `ws.send_json` |

Cosmetic messages (keep `send_to_player` or broadcast — NO `seq`):
- `entity_moved`, `entity_entered`, `entity_left` — broadcast
- `chat`, `party_chat` — broadcast
- `room_state` — full state resync

### handle_reconnect — last_seq Check

After sending `login_success` in both Case 1 and Case 2 of `handle_reconnect`:

```python
# Check if client is up to date
last_seq = data.get("last_seq")
if last_seq is not None:
    current_seq = game.connection_manager.get_msg_seq(entity_id)
    if last_seq == current_seq:
        await websocket.send_json(
            with_request_id({"type": "seq_status", "status": "up_to_date"}, data)
        )
```

Full resync (room_state + combat_state) is always sent regardless of `last_seq` — the `seq_status` message is an additional signal for the client to know if it missed critical messages. The client can use this to decide whether to replay any queued actions.

### Combat Handler Changes

In `_broadcast_combat_state` (`server/net/handlers/combat.py:41-50`), replace:
```python
# Old:
ws = game.connection_manager.get_websocket(eid)
if ws:
    await ws.send_json({"type": "combat_turn", "result": result, **state})

# New:
await game.connection_manager.send_to_player_seq(
    eid, {"type": "combat_turn", "result": result, **state}
)
```

In `_send_combat_end_message` (`server/net/handlers/combat.py:53-70`), replace:
```python
# Old:
ws = game.connection_manager.get_websocket(eid)
if not ws:
    return
...
await ws.send_json({"type": "combat_end", **player_end_result})

# New: Remove the ws/guard entirely — send_to_player_seq handles absent WS internally.
# The message-building code (player_end_result dict construction) does NOT use ws.
await game.connection_manager.send_to_player_seq(
    eid, {"type": "combat_end", **player_end_result}
)
```

### xp.py Changes

In `notify_xp` (`server/core/xp.py:92-112`), replace `ws.send_json` with `connection_manager.send_to_player_seq`:
```python
await game.connection_manager.send_to_player_seq(entity_id, {
    "type": "xp_gained", ...
})
```

In `send_level_up_available` (`server/core/xp.py:151-185`), same pattern:
```python
await game.connection_manager.send_to_player_seq(entity_id, {
    "type": "level_up_available", ...
})
```

### cleanup_session and deferred_cleanup

Both `cleanup_session` and `deferred_cleanup` need to call `game.connection_manager.clear_msg_seq(entity_id)` before `self.remove_session(entity_id)`:

```python
# In cleanup_session (line 77, before disconnect):
game.connection_manager.clear_msg_seq(entity_id)

# In deferred_cleanup (line 95, before remove_session):
game.connection_manager.clear_msg_seq(entity_id)
```

### Files to Modify

| File | Change |
|------|--------|
| `server/net/connection_manager.py:10-84` | Add `_msg_seq`, `get_msg_seq`, `clear_msg_seq`, `send_to_player_seq`, `setdefault` in `connect` |
| `server/net/schemas.py` | Add `last_seq: int \| None = None` to `ReconnectMessage` |
| `server/net/handlers/auth.py:307-465` | `handle_reconnect` checks `last_seq` |
| `server/net/handlers/combat.py:41-70` | `_broadcast_combat_state` and `_send_combat_end_message` use `send_to_player_seq` |
| `server/core/xp.py:92-185` | `notify_xp` and `send_level_up_available` use `send_to_player_seq` |
| `server/net/handlers/trade.py:49-53` | `_send_trade_update` uses `send_to_player_seq` |
| `server/player/manager.py:55-95` | `cleanup_session` and `deferred_cleanup` call `clear_msg_seq` |
| `server/net/outbound_schemas.py` | Add `seq` field to critical message schemas, add `SeqStatusMessage` |
| `tests/test_msg_seq.py` | **New** — message sequence tests |

### Key Patterns

- **No new imports in `ConnectionManager`**: Per ADR-16-3, `ConnectionManager` stays decoupled from game logic
- **`setdefault` in `connect()`**: Initializes to 0 on first login, preserves counter on reconnect
- **Counter increments even without WebSocket**: Ensures consistency during grace period
- **`seq` is additive**: Existing tests don't assert absence of `seq` field, so adding it is backward-compatible

### References

- [Source: epic-16-tech-spec.md#Story-16.11] — Full spec (lines 1541-1631)
- [Source: epics.md#Story-16.11] — BDD acceptance criteria (lines 4539-4585)
- [Source: server/net/connection_manager.py:10-84] — ConnectionManager (add seq tracking)
- [Source: server/net/handlers/combat.py:41-70] — Combat state broadcast + end message
- [Source: server/core/xp.py:92-185] — notify_xp + send_level_up_available
- [Source: server/net/handlers/trade.py:49-53] — Trade update broadcast
- [Source: server/net/handlers/auth.py:307-465] — handle_reconnect (add last_seq check)
- [Source: server/player/manager.py:55-95] — cleanup_session + deferred_cleanup (add clear_msg_seq)
- [Source: epic-16-tech-spec.md ADR-16-3] — msg_seq on ConnectionManager, not PlayerSession

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Completion Notes List

- Added `_msg_seq` dict, `get_msg_seq`, `clear_msg_seq`, `send_to_player_seq` to ConnectionManager
- `send_to_player_seq` creates copy of message dict (`{**message, "seq": seq}`) to prevent aliasing when same dict sent to multiple players
- `send_to_player_seq` includes try/except error guard matching existing `broadcast_to_room` pattern
- Counter increments even without WebSocket (grace period consistency)
- `connect()` uses `setdefault` to preserve counter on reconnect
- `disconnect()` does NOT remove `_msg_seq` (grace period preservation)
- Added `clear_msg_seq` calls to both `cleanup_session` and `deferred_cleanup`
- Added `last_seq: int | None = None` to `ReconnectMessage` schema
- `handle_reconnect` checks `last_seq` in both Case 1 and Case 2, sends `seq_status: up_to_date` if match
- Switched `_broadcast_combat_state` and `_send_combat_end_message` to `send_to_player_seq`
- Removed `if not ws: return` guard from `_send_combat_end_message` (send_to_player_seq handles it)
- Switched `notify_xp` and `send_level_up_available` to `send_to_player_seq`
- Switched `_send_trade_update` to `send_to_player_seq`
- Added `seq` field to 5 outbound schemas + new `SeqStatusMessage`
- Updated test assertions in test_xp.py, test_level_up.py, test_trade.py for new send pattern
- 17 new tests in test_msg_seq.py, 1062 total passing

### File List

- `server/net/connection_manager.py` — Modified: _msg_seq, get_msg_seq, clear_msg_seq, send_to_player_seq, setdefault in connect
- `server/player/manager.py` — Modified: clear_msg_seq in cleanup_session + deferred_cleanup
- `server/net/schemas.py` — Modified: last_seq field on ReconnectMessage
- `server/net/handlers/auth.py` — Modified: handle_reconnect last_seq check
- `server/net/handlers/combat.py` — Modified: _broadcast_combat_state + _send_combat_end_message use send_to_player_seq
- `server/core/xp.py` — Modified: notify_xp + send_level_up_available use send_to_player_seq
- `server/net/handlers/trade.py` — Modified: _send_trade_update uses send_to_player_seq
- `server/net/outbound_schemas.py` — Modified: seq field on 5 schemas + SeqStatusMessage
- `tests/test_xp.py` — Modified: assertion updates for send_to_player_seq
- `tests/test_level_up.py` — Modified: assertion updates for send_to_player_seq
- `tests/test_trade.py` — Modified: added send_to_player_seq mock
- `tests/test_msg_seq.py` — **New**: 17 message sequence tests
