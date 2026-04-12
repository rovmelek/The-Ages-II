# Story 15.3: Handler Auth Middleware

Status: done

## Story

As a developer,
I want a `@requires_auth` decorator that injects `entity_id` and `player_info` into handler functions,
So that the 8-line auth-check boilerplate is not duplicated across 17+ handlers.

## Acceptance Criteria

1. **Given** the repeated auth-check pattern across handlers (post-15.1/15.2 form):
   ```python
   entity_id = game.connection_manager.get_entity_id(websocket)
   if entity_id is None:
       await websocket.send_json({"type": "error", "detail": "Not logged in"})
       return
   player_info = game.player_manager.get_session(entity_id)
   if player_info is None:
       await websocket.send_json({"type": "error", "detail": "Not logged in"})
       return
   ```
   **When** Story 15.3 is implemented,
   **Then** a `@requires_auth` decorator exists in `server/net/auth_middleware.py` that wraps handler functions.

2. **Given** the decorator wraps handler functions,
   **When** a decorated handler is called,
   **Then** the **outer (decorated) function** retains the `(websocket, data, *, game)` signature (lambda registration in `app.py` is unaffected),
   **And** the **inner function** receives additional `entity_id: str` and `player_info: PlayerSession` keyword arguments injected by the decorator,
   **And** unauthenticated requests (entity_id is None OR player_info is None) are rejected with `{"type": "error", "detail": "Not logged in"}` before the inner handler body runs.

3. **Given** 14 handler functions use the full two-step auth check (entity_id + session):
   - `handle_move` (movement.py:36-44)
   - `handle_chat` (chat.py:16-24)
   - `handle_interact` (interact.py:21-29)
   - `handle_inventory` (inventory.py:19-27)
   - `handle_use_item` (inventory.py:44-52)
   - `handle_look` (query.py:29-37)
   - `handle_who` (query.py:72-80)
   - `handle_stats` (query.py:104-112)
   - `handle_help_actions` (query.py:141-149)
   - `handle_map` (query.py:168-176)
   - `handle_trade` (trade.py:57-65)
   - `handle_party` (party.py:121-129)
   - `handle_party_chat` (party.py:576-584)
   - `handle_level_up` (levelup.py:25-33)
   **When** Story 15.3 is implemented,
   **Then** they are decorated with `@requires_auth` and the manual boilerplate is removed,
   **And** handler signatures add `entity_id: str` and `player_info: PlayerSession` keyword params.

4. **Given** 3 combat handlers use only the `entity_id` check (no session check):
   - `handle_play_card` (combat.py:255-258)
   - `handle_flee` (combat.py:289-292)
   - `handle_pass_turn` (combat.py:395-398)
   **And** `handle_use_item_combat` (combat.py:339-342) checks entity_id then combat instance, then session later (line 355-357),
   **When** Story 15.3 is implemented,
   **Then** all 4 combat handlers are also decorated with `@requires_auth` — they receive both `entity_id` and `player_info` (combat participants always have sessions), and the manual entity_id boilerplate is removed.

5. **Given** `handle_logout` (auth.py:26-33) checks only entity_id before calling `cleanup_session`,
   **When** Story 15.3 is implemented,
   **Then** `handle_logout` IS decorated with `@requires_auth` — it receives `entity_id` and `player_info`, then calls `game.player_manager.cleanup_session(entity_id, game)`.

6. **Given** `handle_login` (auth.py:114) and `handle_register` (auth.py:44) do not require auth,
   **When** Story 15.3 is implemented,
   **Then** they are NOT decorated — they keep their current behavior.

7. **Given** all existing tests (807+),
   **When** Story 15.3 is implemented,
   **Then** all tests pass with no assertion value changes.

## Tasks / Subtasks

### Task 1: Create the `@requires_auth` decorator (AC: #1, #2)

- [x] 1.1: Create `server/net/auth_middleware.py` with `requires_auth` decorator
  - Use `functools.wraps` to preserve function metadata
  - Outer wrapper signature: `async def wrapper(websocket: WebSocket, data: dict, *, game: Game) -> None`
  - Perform two checks: `game.connection_manager.get_entity_id(websocket)` then `game.player_manager.get_session(entity_id)`
  - On either None: `await websocket.send_json({"type": "error", "detail": "Not logged in"})` and return
  - On success: `await fn(websocket, data, game=game, entity_id=entity_id, player_info=player_info)`
  - Imports: `from __future__ import annotations`, `functools`, `TYPE_CHECKING` guard for `Game`, `WebSocket` from fastapi, `PlayerSession` from `server.player.session`

### Task 2: Decorate movement handler (AC: #3)

- [x] 2.1: `server/net/handlers/movement.py` — `handle_move`:
  - Add `@requires_auth` decorator, add `entity_id: str` and `player_info: PlayerSession` to signature
  - Remove lines 36-44 (entity_id + player_info boilerplate)
  - Add import: `from server.net.auth_middleware import requires_auth`

### Task 3: Decorate chat handler (AC: #3)

- [x] 3.1: `server/net/handlers/chat.py` — `handle_chat`:
  - Add `@requires_auth` decorator, add params to signature
  - Remove lines 16-24 (boilerplate)
  - Add import: `from server.net.auth_middleware import requires_auth`

### Task 4: Decorate interact handler (AC: #3)

- [x] 4.1: `server/net/handlers/interact.py` — `handle_interact`:
  - Add `@requires_auth` decorator, add params to signature
  - Remove lines 21-29 (boilerplate)
  - Add import: `from server.net.auth_middleware import requires_auth`

### Task 5: Decorate inventory handlers (AC: #3)

- [x] 5.1: `server/net/handlers/inventory.py` — `handle_inventory` and `handle_use_item`:
  - Add `@requires_auth` to both, add params to signatures
  - Remove lines 19-27 (handle_inventory boilerplate) and lines 44-52 (handle_use_item boilerplate)
  - Add import: `from server.net.auth_middleware import requires_auth`

### Task 6: Decorate query handlers (AC: #3)

- [x] 6.1: `server/net/handlers/query.py` — `handle_look`, `handle_who`, `handle_stats`, `handle_help_actions`, `handle_map`:
  - Add `@requires_auth` to all 5, add params to signatures
  - Remove boilerplate from each (lines 29-37, 72-80, 104-112, 141-149, 168-176)
  - Add import: `from server.net.auth_middleware import requires_auth`

### Task 7: Decorate trade handler (AC: #3)

- [x] 7.1: `server/net/handlers/trade.py` — `handle_trade`:
  - Add `@requires_auth`, add params to signature
  - Remove lines 57-65 (boilerplate)
  - Add import: `from server.net.auth_middleware import requires_auth`

### Task 8: Decorate party handlers (AC: #3)

- [x] 8.1: `server/net/handlers/party.py` — `handle_party` and `handle_party_chat`:
  - Add `@requires_auth` to both, add params to signatures
  - Remove lines 121-129 (handle_party boilerplate) and lines 576-584 (handle_party_chat boilerplate)
  - Add import: `from server.net.auth_middleware import requires_auth`

### Task 9: Decorate level-up handler (AC: #3)

- [x] 9.1: `server/net/handlers/levelup.py` — `handle_level_up`:
  - Add `@requires_auth`, add params to signature
  - Remove lines 25-33 (boilerplate)
  - Add import: `from server.net.auth_middleware import requires_auth`

### Task 10: Decorate combat handlers (AC: #4)

- [x] 10.1: `server/net/handlers/combat.py` — `handle_play_card`, `handle_flee`, `handle_pass_turn`, `handle_use_item_combat`:
  - Add `@requires_auth` to all 4, add `entity_id` and `player_info` params to signatures
  - Remove entity_id boilerplate from each (lines 255-258, 289-292, 339-342, 395-398)
  - For `handle_use_item_combat`: also remove the later `player_info = game.player_manager.get_session(entity_id)` check (lines 355-358) since it's now injected
  - Add import: `from server.net.auth_middleware import requires_auth`

### Task 11: Decorate logout handler (AC: #5)

- [x] 11.1: `server/net/handlers/auth.py` — `handle_logout`:
  - Add `@requires_auth`, add `entity_id` and `player_info` params to signature
  - Remove lines 28-33 (entity_id boilerplate)
  - Add import: `from server.net.auth_middleware import requires_auth`

### Task 12: Verify and finalize (AC: #7)

- [x] 12.1: Run `make test` — all 807+ tests must pass
- [x] 12.2: Verify auth boilerplate removed — search for `get_entity_id` in handler files should only appear in: (a) `auth_middleware.py` (the decorator), (b) `auth.py` `handle_login`/`_kick_old_session` (which have their own entity_id logic for different purposes)
- [x] 12.3: Verify no handler signature changes broke registration — `app.py` lambda registration unchanged

## Dev Notes

### Architecture & Patterns

- **Pure refactor** — zero gameplay behavior changes
- **ADR-15-3:** `@requires_auth` in dedicated `auth_middleware.py` — outer function retains `(websocket, data, *, game)` signature; inner function receives additional `entity_id`, `player_info` kwargs
- The decorator uses `functools.wraps` for proper function metadata preservation
- `app.py` lambda registration (`lambda ws, d: handle_X(ws, d, game=self)`) is completely unaffected — the decorated function has the same outer signature

### Decorator Implementation

```python
from __future__ import annotations
import functools
from typing import TYPE_CHECKING
from fastapi import WebSocket
from server.player.session import PlayerSession

if TYPE_CHECKING:
    from server.app import Game

def requires_auth(fn):
    @functools.wraps(fn)
    async def wrapper(websocket: WebSocket, data: dict, *, game: Game) -> None:
        entity_id = game.connection_manager.get_entity_id(websocket)
        if entity_id is None:
            await websocket.send_json({"type": "error", "detail": "Not logged in"})
            return
        player_info = game.player_manager.get_session(entity_id)
        if player_info is None:
            await websocket.send_json({"type": "error", "detail": "Not logged in"})
            return
        await fn(websocket, data, game=game, entity_id=entity_id, player_info=player_info)
    return wrapper
```

### Combat Handlers — Why Decorate?

The 3 combat handlers (`handle_play_card`, `handle_flee`, `handle_pass_turn`) currently only check `entity_id`, not `player_info`. Adding `@requires_auth` adds a `player_info` check. This is safe because:
- Combat participants ALWAYS have active sessions (you can't enter combat without being logged in)
- If a session is somehow missing for a combat participant, returning "Not logged in" is the correct behavior
- `handle_use_item_combat` already checks both entity_id and player_info (at different points) — the decorator unifies this

### handle_logout — Why Decorate?

`handle_logout` currently only checks `entity_id`, not `player_info`. Adding the decorator means `player_info` is also checked. This is correct because:
- If entity_id exists but session is missing, there's nothing to clean up — returning "Not logged in" is appropriate
- The decorator injects `player_info` but logout doesn't need to use it — it only uses `entity_id` for `cleanup_session(entity_id, game)`

### Files NOT Decorated

- `handle_login` (auth.py:114) — pre-auth; handles its own entity_id logic for duplicate login detection
- `handle_register` (auth.py:44) — pre-auth; no entity_id needed
- `_kick_old_session` (auth.py) — internal helper, not a registered handler

### Error Message

All auth checks use the exact same string: `"Not logged in"`. The decorator preserves this.

### Project Structure Notes

- New file: `server/net/auth_middleware.py` — placed in `server/net/` alongside `connection_manager.py` and `message_router.py` (network infrastructure layer)
- No changes to `server/net/__init__.py` needed — handlers import the decorator directly
- `app.py` is NOT modified — handler registration lambdas are unaffected

### Files to Modify

| File | Changes |
|------|---------|
| `server/net/auth_middleware.py` | **NEW** — `requires_auth` decorator |
| `server/net/handlers/movement.py` | Decorate `handle_move`, remove boilerplate |
| `server/net/handlers/chat.py` | Decorate `handle_chat`, remove boilerplate |
| `server/net/handlers/interact.py` | Decorate `handle_interact`, remove boilerplate |
| `server/net/handlers/inventory.py` | Decorate `handle_inventory` + `handle_use_item`, remove boilerplate |
| `server/net/handlers/query.py` | Decorate 5 handlers, remove boilerplate |
| `server/net/handlers/trade.py` | Decorate `handle_trade`, remove boilerplate |
| `server/net/handlers/party.py` | Decorate `handle_party` + `handle_party_chat`, remove boilerplate |
| `server/net/handlers/levelup.py` | Decorate `handle_level_up`, remove boilerplate |
| `server/net/handlers/combat.py` | Decorate 4 handlers, remove entity_id boilerplate |
| `server/net/handlers/auth.py` | Decorate `handle_logout`, remove entity_id boilerplate |

### Anti-Patterns to Avoid

- Do NOT change `app.py` handler registration — the decorator preserves the outer signature
- Do NOT change error messages — they must remain `"Not logged in"` exactly
- Do NOT decorate `handle_login` or `handle_register` — they are pre-auth
- Do NOT change assertion values in any test — pure refactor
- Do NOT change gameplay behavior — this is purely structural
- Do NOT add `player_info` as a positional parameter — it must be keyword-only

### Previous Story Intelligence

From Story 15.2:
- `PlayerManager.cleanup_session(entity_id, game)` exists in `server/player/manager.py`
- Test patches for cleanup path target `server.player.manager.player_repo`
- All 807 tests pass with 0 failures, 0 warnings

From Story 15.1:
- `game.player_manager.get_session(entity_id)` returns `PlayerSession | None`
- `game.connection_manager.get_entity_id(websocket)` returns `str | None`

### Testing Impact

- Tests call handlers directly: `await handle_X(mock_ws, data, game=game)` — this still works because the decorator's wrapper has the same outer signature
- Tests that mock `game.connection_manager.get_entity_id` to return an entity_id and `game.player_manager.get_session` to return a PlayerSession will continue to work — the decorator calls the same methods
- No test assertion values change — the decorator is behaviorally transparent

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Story 15.3 (lines 3691-3737)]
- [Source: _bmad-output/planning-artifacts/epics.md — ADR-15-3 (line 3915)]
- [Source: server/net/handlers/ — all handler files with auth boilerplate]
- [Source: server/app.py — handler registration lambdas (lines 142-233)]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- All 807 tests pass (0 failures, 0 warnings, ~3.9s)
- `grep -r "get_entity_id(websocket)" server/net/handlers/` returns zero hits (only in auth_middleware.py)
- app.py handler registration lambdas unchanged

### Completion Notes List

- Created `server/net/auth_middleware.py` with `@requires_auth` decorator using `functools.wraps`
- Decorated 19 handler functions across 10 files:
  - 14 handlers with full two-step auth pattern: handle_move, handle_chat, handle_interact, handle_inventory, handle_use_item, handle_look, handle_who, handle_stats, handle_help_actions, handle_map, handle_trade, handle_party, handle_party_chat, handle_level_up
  - 4 combat handlers with entity_id-only pattern: handle_play_card, handle_flee, handle_pass_turn, handle_use_item_combat
  - 1 logout handler: handle_logout
- Removed ~160 lines of duplicated auth-check boilerplate
- `handle_login` and `handle_register` remain undecorated (pre-auth handlers)
- Pure refactor — zero gameplay behavior changes

### File List

**New:**
- `server/net/auth_middleware.py` — `@requires_auth` decorator

**Modified:**
- `server/net/handlers/movement.py` — decorated `handle_move`
- `server/net/handlers/chat.py` — decorated `handle_chat`
- `server/net/handlers/interact.py` — decorated `handle_interact`
- `server/net/handlers/inventory.py` — decorated `handle_inventory`, `handle_use_item`
- `server/net/handlers/query.py` — decorated `handle_look`, `handle_who`, `handle_stats`, `handle_help_actions`, `handle_map`
- `server/net/handlers/trade.py` — decorated `handle_trade`
- `server/net/handlers/party.py` — decorated `handle_party`, `handle_party_chat`
- `server/net/handlers/levelup.py` — decorated `handle_level_up`
- `server/net/handlers/combat.py` — decorated `handle_play_card`, `handle_flee`, `handle_pass_turn`, `handle_use_item_combat`
- `server/net/handlers/auth.py` — decorated `handle_logout`
