# Story 12.8: World Map

Status: done

## Story

As a player,
I want to see a map of rooms I've discovered and their connections,
so that I can navigate the game world and plan my exploration.

## Acceptance Criteria

1. **Given** a player sends `/map`, **When** the server processes the request, **Then** the server reads `player_info["visited_rooms"]` from in-memory state, cross-references with room exit data from `RoomManager`, and sends a `map_data` message.

2. **Given** a player has visited `town_square` and `dark_cave`, **When** they send `/map`, **Then** `map_data.rooms` includes only `[{room_key: "town_square", name: "Town Square"}, {room_key: "dark_cave", name: "Dark Cave"}]`. Undiscovered rooms are omitted entirely — player cannot infer total room count or names.

3. **Given** a discovered room has exits to both discovered and undiscovered rooms, **When** connections are built, **Then** connections to discovered rooms show the destination name: `{from_room: "town_square", to_room: "dark_cave", direction: "south"}`. Connections to undiscovered rooms show `"???"` as `to_room`: `{from_room: "town_square", to_room: "???", direction: "east"}`.

4. **Given** a player has visited all 4 rooms, **When** they send `/map`, **Then** all rooms and all connections are shown with full names (no `???`).

5. **Given** a player has visited zero rooms (edge case — should not happen since login adds spawn room to `visited_rooms`), **When** they send `/map`, **Then** they receive an empty map: `{type: "map_data", rooms: [], connections: []}`.

6. **Given** a `room_key` in `visited_rooms` is not found in `RoomManager` (stale data), **When** the map is built, **Then** the stale room is skipped with a `logger.warning(...)` (no error to player).

7. **Given** the `visited_rooms` field already exists on the Player model (added in Story 11.4), **When** Story 12.8 is implemented, **Then** no new DB schema changes are needed — reuse existing `visited_rooms` list.

8. **Given** the web client receives a `map_data` message, **When** the message is rendered, **Then** the client displays a text-based room list in the chat panel. Rooms are listed with their names. Connections show direction and destination (or `???` for undiscovered). The display is visually distinct from chat messages (use `'system'` class).

9. **Given** a player discovers a new room (first visit via room transition), **When** they subsequently send `/map`, **Then** the newly discovered room appears because `visited_rooms` is updated in-memory by `_handle_exit_transition()` in `server/net/handlers/movement.py`.

10. **Given** the `/map` command is implemented, **When** a player sends `/help`, **Then** the server response groups commands by category: Movement (`move`), Combat (`play_card`, `pass_turn`, `flee`, `use_item_combat`), Social (none yet), Info (`look`, `who`, `stats`, `map`, `inventory`, `help_actions`). The client-side `/help` also lists `/map`.

## Tasks / Subtasks

- [x] Task 1: Add `handle_map` to `server/net/handlers/query.py` (AC: #1, #2, #3, #4, #5, #6, #7)
  - [x] 1.1: Follow existing handler pattern (`handle_look`, `handle_who`, etc.) — signature: `async def handle_map(websocket: WebSocket, data: dict, *, game: Game) -> None`
  - [x] 1.2: Get `entity_id` from `game.connection_manager.get_entity_id(websocket)`, get `player_info` from `game.player_entities`, return error if not logged in (same guard pattern as other handlers)
  - [x] 1.3: Read `visited_rooms = player_info.get("visited_rooms", [])` — this is the in-memory list, NOT from DB
  - [x] 1.4: Build rooms list: for each `room_key` in `visited_rooms`, call `game.room_manager.get_room(room_key)`. If room is `None`, log warning and skip. Otherwise add `{"room_key": room.room_key, "name": room.name}`.
  - [x] 1.5: Build connections list: for each visited room, iterate `room.exits` (list of dicts with keys `target_room`, `x`, `y`, `direction`). For each exit: if `exit["target_room"]` is in `visited_rooms` set, use room name from RoomManager lookup; else use `"???"`. Append `{"from_room": room_key, "to_room": target_name_or_question_marks, "direction": exit["direction"]}`.
  - [x] 1.6: Send response: `{"type": "map_data", "rooms": rooms, "connections": connections}`

- [x] Task 2: Register `map` action in `server/app.py` `_register_handlers()` (AC: #1)
  - [x] 2.1: Import `handle_map` from `server.net.handlers.query`
  - [x] 2.2: Register: `self.router.register("map", lambda ws, d: handle_map(ws, d, game=self))`

- [x] Task 3: Update `handle_help_actions` to group by category (AC: #10)
  - [x] 3.1: In `server/net/handlers/query.py`, modify `handle_help_actions` to return actions grouped by category dict instead of flat list
  - [x] 3.2: Categories: `{"Movement": ["move"], "Combat": ["play_card", "pass_turn", "flee", "use_item_combat"], "Items": ["inventory", "use_item", "interact"], "Social": ["chat", "logout"], "Info": ["look", "who", "stats", "map", "help_actions", "level_up"]}`. Note: `login` and `register` are pre-auth actions — exclude from help categories. `interact` is included in Items (interact with objects like chests/levers).
  - [x] 3.3: Response format: `{"type": "help_result", "categories": {category: [action, ...]}}`

- [x] Task 4: Add `/map` command to web client `COMMANDS` in `web-demo/js/game.js` (AC: #8)
  - [x] 4.1: Add `map` entry to `COMMANDS` object: `{handler: () => sendAction('map'), description: 'Show world map', usage: '/map'}`

- [x] Task 5: Handle `map_data` message in web client (AC: #8)
  - [x] 5.1: Add `map_data: handleMapData` entry to the `handlers` lookup object in `onMessage()` (around `game.js:429-453`). The web client uses a handler lookup table (`handlers[data.type]`), NOT a switch statement.
  - [x] 5.2: Create `handleMapData(data)` function: format as text in chat — header line "=== World Map ===", then list rooms by name, then list connections as "Room → Destination (direction)" or "Room → ??? (direction)"
  - [x] 5.3: Use `appendChat(line, 'system')` for system-styled output

- [x] Task 6: Write tests for `handle_map` (AC: #1-#7, #9)
  - [x] 6.1: Create `tests/test_map.py`
  - [x] 6.2: `test_map_not_logged_in` — no entity_id returns error
  - [x] 6.3: `test_map_no_visited_rooms` — empty visited_rooms returns empty map
  - [x] 6.4: `test_map_single_room` — one visited room shows room + connections with `???` destinations
  - [x] 6.5: `test_map_multiple_rooms` — two visited rooms show both rooms and resolved connections
  - [x] 6.6: `test_map_all_rooms_visited` — all 4 rooms show complete map with no `???`
  - [x] 6.7: `test_map_stale_room_skipped` — room_key in visited_rooms but not in RoomManager is skipped (warning logged)
  - [x] 6.8: `test_map_connections_undiscovered_shown_as_question_marks` — exits to unvisited rooms show `???`
  - [x] 6.9: Update `test_help_actions_returns_registered` in `tests/test_query.py` to match new categorized response format (`response["categories"]` dict instead of `response["actions"]` list)

- [x] Task 7: Update `/help` display in web client (AC: #10)
  - [x] 7.1: If `handle_help_actions` now returns categories, update web client `help_result` handler to display grouped output

## Dev Notes

### Architecture Compliance

- **Handler pattern**: All query handlers follow the same structure — see `handle_look`, `handle_who`, `handle_stats` in `server/net/handlers/query.py`. Use identical guard pattern (check entity_id, check player_info).
- **Handler signature**: `async def handle_map(websocket: WebSocket, data: dict, *, game: Game) -> None`
- **Import guard**: `from __future__ import annotations` is already first import in `query.py`. `Game` is already under `TYPE_CHECKING`.
- **Registration**: In `server/app.py:_register_handlers()`, add import and lambda registration matching existing pattern (line 132-191).
- **No DB access needed**: `visited_rooms` is in-memory (`player_info["visited_rooms"]`). Room exits are in-memory (`room.exits`). ADR-6 says map data computed on request, no caching.
- **Room topology**: 4 rooms in circular loop: `town_square ↔ test_room ↔ other_room ↔ dark_cave ↔ town_square`. Exits also include vertical: `town_square` has a `"descend"` exit to `dark_cave`.

### Data Sources

- **`visited_rooms`**: Stored in `player_info["visited_rooms"]` (list of room_key strings). Populated by `_handle_exit_transition()` in `server/net/handlers/movement.py:247-257`. Restored on login in `server/net/handlers/auth.py:299-309`. Persisted on disconnect in `auth.py:88-91`.
- **Room exits**: `room.exits` is a `list[dict]` loaded from room JSON. Each exit dict has keys: `target_room` (str), `x` (int), `y` (int), `direction` (str), `entry_x` (int), `entry_y` (int). Direction values include movement directions (`"south"`, `"east"`, `"west"`, `"north"`) and vertical (`"ascend"`, `"descend"`).
- **Room names**: `room.name` (str) on `RoomInstance` — e.g., `"Town Square"`, `"Dark Cave"`, `"Test Room"`, `"Other Room"`.
- **RoomManager lookup**: `game.room_manager.get_room(room_key)` returns `RoomInstance | None`. The `_rooms` dict contains all loaded rooms.

### Testing Standards

- Test file: `tests/test_map.py` — flat structure matching existing tests
- Use `AsyncMock` for WebSocket, direct `Game()` instantiation for unit tests
- Follow patterns from `tests/test_query.py` (if exists) or `tests/test_game.py`
- No DB needed — all data is in-memory
- Mock `game.connection_manager.get_entity_id` to return entity_id
- Set up `game.player_entities[entity_id]` with `visited_rooms` list
- Set up `game.room_manager._rooms` with test `RoomInstance` objects

### Web Client Notes

- `COMMANDS` object at `web-demo/js/game.js:146` — add `map` entry following same structure
- WebSocket message dispatch uses a handler lookup object (`handlers[data.type]`) at `game.js:429-456`, NOT a switch statement. Add `map_data: handleMapData` entry and create the `handleMapData(data)` function.
- Existing `handleHelpResult` at `game.js:894-898` expects `data.actions` array — must be updated to handle new categorized format (`data.categories` dict). See Task 7.
- Use `appendChat(text, 'system')` for output (system class provides visual distinction)
- `sendAction('map')` sends `{action: "map"}` over WebSocket

### Project Structure Notes

- All changes fit within existing directory structure — new file: `tests/test_map.py`; modified files listed below
- Server changes: `server/net/handlers/query.py` (add `handle_map`, modify `handle_help_actions`), `server/app.py` (register handler)
- Client changes: `web-demo/js/game.js` (add `/map` command, add `map_data` handler, update `handleHelpResult`)
- Test changes: `tests/test_map.py` (new), `tests/test_query.py` (update `test_help_actions_returns_registered` for new categorized format)

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 12.8: World Map] — AC and implementation notes
- [Source: _bmad-output/planning-artifacts/architecture.md#Epic 12: Social Systems] — ADR-6 (map computed on request), response format
- [Source: _bmad-output/project-context.md#Epic 12] — World map reuses visited_rooms, no new DB schema
- [Source: server/net/handlers/query.py] — existing handler patterns (handle_look, handle_who, handle_stats, handle_help_actions)
- [Source: server/app.py:118-191] — handler registration pattern
- [Source: server/net/handlers/movement.py:247-257] — visited_rooms population
- [Source: server/net/handlers/auth.py:299-309] — visited_rooms restore on login
- [Source: server/room/room.py:39] — RoomInstance.exits field (list[dict])
- [Source: web-demo/js/game.js:146-253] — COMMANDS object and slash command infrastructure
- [Source: _bmad-output/implementation-artifacts/11-4-exploration-and-interaction-xp-sources.md] — visited_rooms implementation details

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Added `handle_map` handler: reads visited_rooms from player_info, builds rooms and connections lists, filters undiscovered destinations to "???", logs warning for stale room_keys
- Registered `map` action in Game._register_handlers()
- Updated `handle_help_actions` to return categorized response format (`categories` dict) instead of flat sorted list
- Added `/map` client command and `handleMapData` message handler with text-based room/connection display
- Updated `handleHelpResult` to support both old (`actions`) and new (`categories`) response formats
- Created 7 tests in `tests/test_map.py` covering all ACs (not-logged-in, empty, single room, multiple rooms, all rooms, stale room, undiscovered)
- Updated `test_help_actions_returns_registered` → `test_help_actions_returns_categories` in `tests/test_query.py`
- All 608 tests pass (601 existing + 7 new), zero regressions

### File List

- server/net/handlers/query.py (modified — added handle_map, updated handle_help_actions to categorized format, added logger)
- server/app.py (modified — imported and registered handle_map)
- web-demo/js/game.js (modified — added /map command, handleMapData, map_data handler, updated handleHelpResult)
- tests/test_map.py (new — 7 tests for handle_map)
- tests/test_query.py (modified — updated help_actions test for categorized format)
- tests/test_exploration_xp.py (modified — added trade_manager mock for _cleanup_player compatibility)
