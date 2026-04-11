# Story 10.4: Server Query Actions

Status: done

## Story

As a player,
I want to query the server for information about my surroundings, who's online, and my stats,
so that I can make informed decisions without relying on UI-only displays.

## Acceptance Criteria

1. **Given** a logged-in player sends `{"action": "look"}`, **When** the server processes the action, **Then** the player receives `{"type": "look_result"}` containing:
   - Interactive objects on the player's tile and all 4 adjacent tiles (with object id, type, direction)
   - NPCs on/adjacent to the player (with name, alive status, direction)
   - Other players on/adjacent to the player (with name, direction)

2. **Given** a logged-in player sends `{"action": "who"}`, **When** the server processes the action, **Then** the player receives `{"type": "who_result", "room": "<room_key>", "players": [{"name": "hero", "x": 50, "y": 50}, ...]}`.

3. **Given** a logged-in player sends `{"action": "stats"}`, **When** the server processes the action, **Then** the player receives `{"type": "stats_result", "stats": {"hp": 85, "max_hp": 100, "attack": 10, "xp": 150}}`.

4. **Given** a logged-in player sends `{"action": "help_actions"}`, **When** the server processes the action, **Then** the player receives `{"type": "help_result", "actions": ["move", "chat", "interact", "inventory", "use_item", "look", "who", "stats", "logout", ...]}`.

5. **Given** a player is not logged in, **When** they send any query action, **Then** the client receives an error: "Not logged in".

6. **And** all new handlers are registered in `Game._register_handlers()`, tests are added for each new action, and `pytest tests/` passes.

## Tasks / Subtasks

- [x] Task 1: Create query handler module (AC: #1-#5)
  - [x] 1.1: Create `server/net/handlers/query.py` with `from __future__ import annotations`, `TYPE_CHECKING` guard for `Game` import
  - [x] 1.2: Implement `handle_look(websocket, data, *, game)` — standard preamble (entity_id + player_info guard), then scan player tile + 4 adjacent tiles for interactive objects, NPCs, and other players
  - [x] 1.3: Implement `handle_who(websocket, data, *, game)` — return all players in the same room
  - [x] 1.4: Implement `handle_stats(websocket, data, *, game)` — return the requesting player's stats dict
  - [x] 1.5: Implement `handle_help_actions(websocket, data, *, game)` — return the list of registered action names from `game.router`

- [x] Task 2: Implement `handle_look` detail (AC: #1)
  - [x] 2.1: Get player position from `entity.x`, `entity.y`; get room via `game.room_manager.get_room(player_info["room_key"])` — guard against `None` (return error "Room not found")
  - [x] 2.2: Hardcode the 5 scan positions as a list of `(dx, dy, label)` tuples: `[(0, 0, "here"), (0, -1, "up"), (0, 1, "down"), (-1, 0, "left"), (1, 0, "right")]`. Do NOT import `DIRECTION_DELTAS` — the hardcoded list is clearer and includes the center tile
  - [x] 2.3: For each `(dx, dy, label)`, compute `(tx, ty) = (entity.x + dx, entity.y + dy)`. Skip if out of bounds (`tx < 0 or ty < 0 or tx >= room.width or ty >= room.height`)
  - [x] 2.4: Scan `room._interactive_objects` (dict values) for objects at each scanned tile — include `{"id": obj["id"], "type": obj["type"], "direction": direction_label}`
  - [x] 2.5: Scan `room._npcs` (dict values) for NPCs at each scanned tile — include ALL NPCs (alive and dead) with `{"name": npc.name, "alive": npc.is_alive, "direction": direction_label}`. Dead NPCs are included so the player knows a corpse is there; the `alive` field lets the client decide how to display them
  - [x] 2.6: Scan `room._entities` (dict values) for other players at each scanned tile — exclude self by comparing `e.id != entity_id` (use entity ID, not name). Include `{"name": e.name, "direction": direction_label}`
  - [x] 2.7: Return `{"type": "look_result", "objects": [...], "npcs": [...], "players": [...]}`

- [x] Task 3: Implement `handle_who` detail (AC: #2)
  - [x] 3.1: Get room from `game.room_manager.get_room(player_info["room_key"])` — guard against `None` (return error "Room not found")
  - [x] 3.2: Iterate `room._entities` values, build list of `{"name": e.name, "x": e.x, "y": e.y}` for ALL players including the requester (this is intentional — `/who` shows everyone in the room)
  - [x] 3.3: Return `{"type": "who_result", "room": player_info["room_key"], "players": [...]}`

- [x] Task 4: Implement `handle_stats` detail (AC: #3)
  - [x] 4.1: Read `entity.stats` from `player_info["entity"]`
  - [x] 4.2: Build response using `.get()` with defaults for each key: `{"hp": stats.get("hp", 100), "max_hp": stats.get("max_hp", 100), "attack": stats.get("attack", 10), "xp": stats.get("xp", 0)}` — handles cases where keys may be missing from older accounts or freshly initialized stats
  - [x] 4.3: Return `{"type": "stats_result", "stats": {...}}` — only these 4 whitelisted keys, do NOT expose `shield` or any transient combat stats

- [x] Task 5: Implement `handle_help_actions` detail (AC: #4)
  - [x] 5.1: Access registered action names from `game.router` — the `MessageRouter` stores handlers in `self._handlers` dict, so `list(game.router._handlers.keys())` gives the action names
  - [x] 5.2: Return `{"type": "help_result", "actions": sorted_action_list}`

- [x] Task 6: Register handlers in `Game._register_handlers()` (AC: #6)
  - [x] 6.1: In `server/app.py` `_register_handlers()` method, import `handle_look`, `handle_who`, `handle_stats`, `handle_help_actions` from `server.net.handlers.query`
  - [x] 6.2: Register: `self.router.register("look", lambda ws, d: handle_look(ws, d, game=self))` — same pattern for `who`, `stats`, `help_actions`

- [x] Task 7: Write tests (AC: #1-#6)
  - [x] 7.1: Create `tests/test_query.py` with tests for all 4 handlers
  - [x] 7.2: `test_look_returns_nearby_entities` — place player, NPC, interactive object, and another player at/adjacent to player position, verify `look_result` contains all with correct direction labels
  - [x] 7.3: `test_look_excludes_self` — verify the requesting player is NOT listed in the `players` field
  - [x] 7.4: `test_look_empty_area` — player in empty area, verify empty lists returned
  - [x] 7.5: `test_who_returns_room_players` — multiple players in room, verify all listed with positions
  - [x] 7.6: `test_stats_returns_player_stats` — set known stats on entity, verify response matches
  - [x] 7.7: `test_stats_excludes_transient` — set `shield` in stats, verify it's NOT in response
  - [x] 7.8: `test_help_actions_returns_registered` — `Game()` calls `_register_handlers()` in `__init__`, so all actions are registered. Verify response `actions` list includes at least: `move`, `chat`, `look`, `who`, `stats`, `help_actions`, `logout`, `interact`, `inventory`
  - [x] 7.9: `test_query_not_logged_in` — verify all 4 actions return "Not logged in" error when `connection_manager.get_entity_id()` returns `None` (no WebSocket mapping)
  - [x] 7.10: `test_who_solo_player` — player alone in room, verify response contains exactly 1 player entry (themselves)
  - [x] 7.11: `test_look_dead_npc` — place a dead NPC (is_alive=False) adjacent to player, verify it appears in `npcs` list with `"alive": False`
  - [x] 7.12: `test_look_object_on_player_tile` — place an interactive object at the player's exact position, verify it appears in `objects` list with `"direction": "here"`. Note: in gameplay players can't stand on interactive objects (Story 10.2 made them blocking), but the handler scans by coordinate matching so this tests the "here" label code path
  - [x] 7.13: Verify `pytest tests/` passes with zero failures

## Dev Notes

### Handler Pattern — Follow Exactly

Every handler in `server/net/handlers/` follows this exact pattern (see `inventory.py` as reference):

```python
"""Query handlers for WebSocket clients."""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import WebSocket

if TYPE_CHECKING:
    from server.app import Game


async def handle_look(
    websocket: WebSocket, data: dict, *, game: Game
) -> None:
    entity_id = game.connection_manager.get_entity_id(websocket)
    if entity_id is None:
        await websocket.send_json({"type": "error", "detail": "Not logged in"})
        return

    player_info = game.player_entities.get(entity_id)
    if player_info is None:
        await websocket.send_json({"type": "error", "detail": "Not logged in"})
        return
    # ... handler logic
```

### Accessing Room Data

- Get room: `game.room_manager.get_room(player_info["room_key"])` returns `RoomInstance`
- Player entities: `room._entities` — `dict[str, PlayerEntity]` keyed by entity_id (underscore-prefixed but no public accessor for listing all exists; `get_player_ids()` only returns IDs)
- NPCs: `room._npcs` — `dict[str, NpcEntity]` keyed by NPC id (no public "list all NPCs" method exists)
- Interactive objects: `room._interactive_objects` — `dict[str, dict]` keyed by object id (raw dicts with `x`, `y`, `type`, `id` fields)
- Player position: `entity.x`, `entity.y` from `player_info["entity"]`
- **Note:** Accessing `_entities`, `_npcs`, `_interactive_objects` directly is intentional — RoomInstance has no public list-all accessors for these. This is consistent with how `get_state()` in `room.py` accesses them internally.

### Direction Computation for `look`

Hardcode a local list of `(dx, dy, label)` tuples — do NOT import `DIRECTION_DELTAS` (it doesn't include center):

```python
_SCAN_OFFSETS = [
    (0, 0, "here"),
    (0, -1, "up"),
    (0, 1, "down"),
    (-1, 0, "left"),
    (1, 0, "right"),
]
```

Scanning loop sketch:

```python
objects, npcs, players = [], [], []
for dx, dy, label in _SCAN_OFFSETS:
    tx, ty = entity.x + dx, entity.y + dy
    if tx < 0 or ty < 0 or tx >= room.width or ty >= room.height:
        continue
    for obj in room._interactive_objects.values():
        if obj["x"] == tx and obj["y"] == ty:
            objects.append({"id": obj["id"], "type": obj["type"], "direction": label})
    for npc in room._npcs.values():
        if npc.x == tx and npc.y == ty:
            npcs.append({"name": npc.name, "alive": npc.is_alive, "direction": label})
    for e in room._entities.values():
        if e.id != entity_id and e.x == tx and e.y == ty:
            players.append({"name": e.name, "direction": label})
```

### NpcEntity Fields

`NpcEntity` is a `@dataclass` in `server/room/objects/npc.py` with fields: `id`, `npc_key`, `name`, `x`, `y`, `behavior_type`, `stats` (dict), `loot_table` (str), `is_alive` (bool), `in_combat` (bool), `spawn_config` (dict). Use `npc.name`, `npc.is_alive` for the look result.

### Stats Whitelist for `stats` Response

Only return: `hp`, `max_hp`, `attack`, `xp`. Do NOT expose `shield` (combat-only transient) or any unknown keys. Use `.get()` with defaults (`hp=100`, `max_hp=100`, `attack=10`, `xp=0`) since keys may be absent from older accounts. This mirrors the server's `_STATS_WHITELIST` in `player/repo.py`.

### `help_actions` — Reading Router State

`MessageRouter` (`server/net/message_router.py`) stores handlers in `self._handlers: dict[str, Callable]`. Access via `game.router._handlers.keys()` — the underscore prefix is internal but acceptable for this read-only introspection. Return a sorted list for deterministic output. Note: action names are raw internal strings (e.g., `use_item_combat`, `pass_turn`) — this is intentional for the prototype; the client-side `/help` command (Story 10.3) already provides human-readable descriptions, so `help_actions` serves as a machine-readable complement.

### Registration in `_register_handlers()`

Add to `server/app.py` `_register_handlers()` (currently at line ~116). Import all 4 handlers from `server.net.handlers.query` inside the method (lazy import pattern used throughout). Register using the same lambda closure pattern:

```python
from server.net.handlers.query import (
    handle_help_actions,
    handle_look,
    handle_stats,
    handle_who,
)
self.router.register("look", lambda ws, d: handle_look(ws, d, game=self))
self.router.register("who", lambda ws, d: handle_who(ws, d, game=self))
self.router.register("stats", lambda ws, d: handle_stats(ws, d, game=self))
self.router.register("help_actions", lambda ws, d: handle_help_actions(ws, d, game=self))
```

### Test Pattern — Follow Existing Handler Tests

Use the same pattern as `tests/test_chat.py` (see `_make_game()` and `_setup_two_players()` there):
- Create a `Game()` instance via `_make_game()` (calls `__init__` which registers handlers)
- Create `RoomInstance` and assign to `game.room_manager._rooms["test"] = room` (direct dict assignment, NOT mocking `get_room`)
- Create `PlayerEntity` instances and add to room via `room.add_entity()`
- Create `AsyncMock` WebSockets and register via `game.connection_manager.connect(entity_id, ws, room_key)`
- Register in `game.player_entities[entity_id] = {"entity": entity, "room_key": "test", "db_id": N}`
- Call handler directly: `await handle_look(ws, {"action": "look"}, game=game)`
- Assert via `ws.send_json.assert_called_with(expected_dict)`

### Previous Story Learnings (from 10.3)

- Story 10.3 created the client-side slash command parser with `COMMANDS` registry in `web-demo/js/game.js`
- Story 10.6 will wire `look`, `who`, `stats` into that parser — this story only creates the **server-side handlers**
- No web client changes in this story — server only

### Design Decisions (Intentional for Prototype)

- **`who` exposes player coordinates** — AC explicitly requires `x`, `y` in the response. This lets players see where everyone is. Acceptable for prototype; production may restrict to "same area" or remove coordinates.
- **`look` includes dead NPCs** — dead NPCs appear with `alive: false` so the player knows a corpse is there. The client can choose to display or hide them.
- **`help_actions` returns raw action strings** — internal names like `use_item_combat` are returned as-is. The client `/help` command provides the human-readable version.

### What NOT to Do

- Do NOT modify any existing handler files — this story only adds new handlers
- Do NOT add client-side slash commands — that's Story 10.6
- Do NOT add new fields to `PlayerEntity` or `NpcEntity` — use existing data
- Do NOT access `room._grid` — `look` only needs entities, NPCs, and interactive objects
- Do NOT persist anything — these are read-only query handlers with no state mutations
- `handle_stats` and `handle_help_actions` do NOT need room access — `stats` reads from `player_info["entity"].stats`, `help_actions` reads from `game.router._handlers`. Only `look` and `who` need the room

### Project Structure Notes

- New file: `server/net/handlers/query.py` — all 4 query handlers in one module (they're all lightweight read-only queries)
- Modified: `server/app.py` — 4 new handler registrations in `_register_handlers()`
- New file: `tests/test_query.py` — tests for all 4 handlers
- No other files modified

### References

- [Source: server/net/handlers/inventory.py] — handler pattern reference
- [Source: server/net/handlers/interact.py] — adjacency check pattern (used in look)
- [Source: server/room/room.py] — RoomInstance API, DIRECTION_DELTAS, _entities, _npcs, _interactive_objects
- [Source: server/player/entity.py] — PlayerEntity dataclass (id, name, x, y, stats)
- [Source: server/net/message_router.py] — MessageRouter._handlers for help_actions
- [Source: server/app.py#_register_handlers] — registration pattern
- [Source: _bmad-output/planning-artifacts/epics.md#Story 10.4] — acceptance criteria
- [Source: _bmad-output/project-context.md] — critical implementation rules

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- Fixed `_setup_player` helper: empty dict `{}` is falsy in Python, so `stats or default` skipped it — changed to `stats if stats is not None else dict(_DEFAULT_STATS)`
- `Game.__init__` does NOT call `_register_handlers()` — that happens in `startup()`. Tests for `help_actions` must call `game._register_handlers()` explicitly
- `test_play_card_kills_mob` hangs in test suite (pre-existing, not related to this story)

### Completion Notes List

- Created `server/net/handlers/query.py` with 4 handlers: `handle_look`, `handle_who`, `handle_stats`, `handle_help_actions`
- All handlers follow the standard preamble pattern (entity_id + player_info guard → "Not logged in" error)
- `handle_look` scans player tile + 4 adjacent tiles for interactive objects, NPCs, and other players using `_SCAN_OFFSETS`; excludes self from player list; includes dead NPCs with `alive: false`; skips out-of-bounds tiles
- `handle_who` returns all players in room including requester with name, x, y
- `handle_stats` returns whitelisted stats (hp, max_hp, attack, xp) with `.get()` defaults for missing keys
- `handle_help_actions` returns sorted list of registered action names from `game.router._handlers`
- Registered all 4 handlers in `Game._register_handlers()` in `server/app.py`
- 12 tests in `tests/test_query.py`: look (5 tests), who (2), stats (3), help_actions (1), not-logged-in (1)
- 510 tests pass, 0 failures, 3 deselected (known hangers)

### Change Log

- 2026-04-10: Story 10.4 implemented — server query actions (look, who, stats, help_actions)

### File List

- server/net/handlers/query.py (new — 4 query handlers)
- server/app.py (modified — 4 new handler registrations in _register_handlers)
- tests/test_query.py (new — 12 tests for query handlers)
