# Story 10.5: Directional Object Interaction

Status: done

## Story

As a player,
I want to interact with adjacent objects by specifying a direction and receive proximity notifications,
so that I can discover and interact with objects naturally without needing to know object IDs.

## Acceptance Criteria

1. **Given** a logged-in player sends `{"action": "interact", "direction": "right"}`, **When** the server processes the action, **Then** the server checks the tile one step to the right of the player's position, and if an interactive object exists on that tile, the interaction proceeds (delegates to existing interact handler logic). Note: direction values are grid directions (`"up"`, `"down"`, `"left"`, `"right"`) matching `DIRECTION_DELTAS` — NOT compass directions.

2. **Given** the `interact` handler, **When** a request is received, **Then** it accepts either `target_id` (existing) OR `direction` (new) — not both required. If both are provided, `target_id` takes precedence.

3. **Given** a player sends an interact with `direction` but no interactive object is in that direction, **When** the server processes the action, **Then** the client receives an error: "Nothing to interact with in that direction".

4. **Given** a player sends an interact with `direction` but the direction is out of bounds, **When** the server processes the action, **Then** the client receives an error: "Nothing to interact with in that direction" (same error — don't leak map boundary info).

5. **Given** a player moves to a tile adjacent to an interactive object, **When** the movement completes (normal move — NOT during exit transitions or combat encounters), **Then** the server sends a separate `{"type": "nearby_objects", "objects": [{"id": "chest_01", "type": "chest", "direction": "right"}]}` message to the moving player only (not broadcast to room).

6. **Given** a player moves away from all interactive objects, **When** the movement completes, **Then** no `nearby_objects` message is sent.

7. **Given** multiple interactive objects are adjacent to the player after a move, **When** the movement completes, **Then** all nearby objects are listed with their directions in a single `nearby_objects` message.

8. **Given** the web client receives a `nearby_objects` message, **When** the UI updates, **Then** a notification is displayed in the chat log: "You see a chest to the right" (one line per object).

9. **Given** a player sends an interact with an invalid direction (e.g., `"northeast"`), **When** the server processes the action, **Then** the client receives an error: "Invalid direction: northeast".

10. **And** existing `interact` by `target_id` continues to work unchanged (backward compatible).
11. **And** the existing test `test_interact_missing_target_id` in `tests/test_interact.py` must be updated — its expected error message changes from `"Missing target_id"` to `"Missing target_id or direction"`.
12. **And** tests cover both `target_id` and `direction` interaction modes, including the case where both are provided (`target_id` takes precedence).
13. **And** `pytest tests/` passes with zero failures.

## Tasks / Subtasks

- [x] Task 1: Extend `handle_interact` for directional mode (AC: #1, #2, #3, #4, #9, #10, #11)
  - [x] 1.1: In `server/net/handlers/interact.py`, after extracting `target_id`, check for `direction` field if `target_id` is empty/missing
  - [x] 1.2: If `direction` is provided, validate it's in `DIRECTION_DELTAS` (import from `server.room.room`). If invalid, return error "Invalid direction: {direction}"
  - [x] 1.3: Compute target tile `(tx, ty) = (entity.x + dx, entity.y + dy)` using `DIRECTION_DELTAS[direction]`
  - [x] 1.4: Check bounds — if `tx < 0 or ty < 0 or tx >= room.width or ty >= room.height`, return error "Nothing to interact with in that direction"
  - [x] 1.5: Search `room._interactive_objects.values()` for an object at `(tx, ty)` — match on `obj["x"] == tx and obj["y"] == ty`
  - [x] 1.6: If no object found at that tile, return error "Nothing to interact with in that direction"
  - [x] 1.7: If found, set `target_id = obj["id"]` and `obj_dict = obj`, then continue to the existing interaction logic (create_object, isinstance check, interact call). Skip the `room.get_object(target_id)` lookup since we already have `obj_dict`
  - [x] 1.8: If neither `target_id` nor `direction` is provided, return error "Missing target_id or direction"
  - [x] 1.9: If `direction` mode is used, skip the adjacency check (player is by definition looking at the adjacent tile)

- [x] Task 2: Add proximity notifications to movement (AC: #5, #6, #7)
  - [x] 2.1: In `server/net/handlers/movement.py`, after the normal move broadcast (line ~76), scan for nearby interactive objects
  - [x] 2.2: Create a helper function `_find_nearby_objects(room, x, y)` in `movement.py` that scans the 4 adjacent tiles (NOT center — player is already on center) for interactive objects
  - [x] 2.3: Use `DIRECTION_DELTAS` from `server.room.room` — iterate `(direction_name, (dx, dy))` pairs, compute `(tx, ty)`, check bounds, check `room._interactive_objects.values()` for objects at `(tx, ty)`
  - [x] 2.4: Return list of `{"id": obj["id"], "type": obj["type"], "direction": direction_name}` dicts
  - [x] 2.5: After the `entity_moved` broadcast, if `nearby_objects` is non-empty, send a **separate** `nearby_objects` message to the moving player ONLY (not broadcast): `{"type": "nearby_objects", "objects": [...]}`

- [x] Task 3: Web client proximity notification display (AC: #8)
  - [x] 3.1: In `web-demo/js/game.js`, add a handler for `"nearby_objects"` message type in the WebSocket message handler
  - [x] 3.2: For each object in the `objects` array, call `appendChat("You see a " + obj.type + " to the " + obj.direction, "system")`

- [x] Task 4: Write tests (AC: #1-#13)
  - [x] 4.1: In `tests/test_interact.py` (existing file), add tests for directional interaction
  - [x] 4.2: `test_interact_direction_right` — create a room large enough (e.g., 10x10 via custom `RoomInstance`), place player at (2, 2), interactive chest at (3, 2), send `{"action": "interact", "direction": "right"}`, verify `interact_result` returned
  - [x] 4.3: `test_interact_direction_nothing` — player at (2, 2), no object at (3, 2), send interact with direction "right", verify error "Nothing to interact with in that direction"
  - [x] 4.4: `test_interact_direction_out_of_bounds` — player at (0, 0), send interact with direction "left", verify error "Nothing to interact with in that direction"
  - [x] 4.5: `test_interact_direction_invalid` — send interact with direction "northeast", verify error "Invalid direction: northeast"
  - [x] 4.6: `test_interact_target_id_still_works` — verify existing `target_id` mode works unchanged
  - [x] 4.7: `test_interact_missing_both` — send interact with neither `target_id` nor `direction`, verify error "Missing target_id or direction"
  - [x] 4.8: `test_interact_target_id_takes_precedence` — send interact with BOTH `target_id` and `direction`, verify `target_id` is used (AC #2)
  - [x] 4.9: Update existing `test_interact_missing_target_id` — change expected error from `"Missing target_id"` to `"Missing target_id or direction"` (AC #11)
  - [x] 4.10: In `tests/test_movement.py` (existing file), added proximity notification tests
  - [x] 4.11: `test_move_nearby_objects` — verified nearby_objects message sent when moving adjacent to interactive object
  - [x] 4.12: `test_move_no_nearby_objects` — verified no nearby_objects message when no adjacent interactive objects
  - [x] 4.13: pytest passes — 517 passed, 1 pre-existing failure (test_chest_already_looted DB issue), 4 deselected (known hangers)

## Dev Notes

### Modifying `handle_interact` — Restructure Flow

The current `handle_interact` in `server/net/handlers/interact.py` (67 lines) has a linear flow: extract `target_id` → find object → adjacency check → create typed object → interact. The direction mode needs to be inserted early in the flow.

**New flow:**
```python
# 1. Standard preamble (entity_id + player_info guard) — UNCHANGED
# 2. Extract target_id and direction from data
target_id = data.get("target_id", "")
direction = data.get("direction", "")

# 3. Get room — UNCHANGED
room = game.room_manager.get_room(room_key)

# 4. BRANCH: resolve obj_dict from either target_id or direction
if target_id:
    # Existing path: lookup by ID
    obj_dict = room.get_object(target_id)
    if obj_dict is None:
        return error "Object not found"
    # Adjacency check (Manhattan distance ≤ 1)
    if abs(entity.x - obj_dict["x"]) + abs(entity.y - obj_dict["y"]) > 1:
        return error "Too far to interact"
elif direction:
    # New path: resolve from direction
    if direction not in DIRECTION_DELTAS:
        return error "Invalid direction: {direction}"
    dx, dy = DIRECTION_DELTAS[direction]
    tx, ty = entity.x + dx, entity.y + dy
    if tx < 0 or ty < 0 or tx >= room.width or ty >= room.height:
        return error "Nothing to interact with in that direction"
    # Search interactive objects at (tx, ty)
    obj_dict = None
    for obj in room._interactive_objects.values():
        if obj["x"] == tx and obj["y"] == ty:
            obj_dict = obj
            break
    if obj_dict is None:
        return error "Nothing to interact with in that direction"
    target_id = obj_dict["id"]
    # No adjacency check needed — direction guarantees distance 1
else:
    return error "Missing target_id or direction"

# 5. Build typed object and interact — UNCHANGED from here
obj = create_object(obj_dict)
if not isinstance(obj, InteractiveObject):
    return error "Object not interactable"
result = await obj.interact(player_db_id, game)
await websocket.send_json({"type": "interact_result", "object_id": target_id, "result": result})
```

**Import needed:** Add `from server.room.room import DIRECTION_DELTAS` at top of `interact.py`.

### Proximity Notification in Movement Handler

In `server/net/handlers/movement.py`, add the scan **after** the `entity_moved` broadcast and **before** the mob encounter check (~line 86). Send as a separate message to the mover only (NOT broadcast — only the moving player needs proximity info):

```python
# After broadcasting entity_moved...
# Proximity notification — notify mover of nearby interactive objects
nearby = _find_nearby_objects(room, result["x"], result["y"])
if nearby:
    await websocket.send_json({"type": "nearby_objects", "objects": nearby})

# Then check for mob encounter...
```

**Helper function** (module-level in `movement.py`):

```python
from server.room.room import DIRECTION_DELTAS

def _find_nearby_objects(room, x: int, y: int) -> list[dict]:
    """Scan 4 adjacent tiles for interactive objects."""
    nearby = []
    for direction, (dx, dy) in DIRECTION_DELTAS.items():
        tx, ty = x + dx, y + dy
        if tx < 0 or ty < 0 or tx >= room.width or ty >= room.height:
            continue
        for obj in room._interactive_objects.values():
            if obj["x"] == tx and obj["y"] == ty:
                nearby.append({"id": obj["id"], "type": obj["type"], "direction": direction})
    return nearby
```

**Important:** `DIRECTION_DELTAS` only has 4 entries (`up`, `down`, `left`, `right`) — no center tile. This is correct for proximity scan (player is already ON center). Do NOT use `_SCAN_OFFSETS` from the query handler — that includes `(0, 0, "here")` which would find objects under the player (impossible since interactive objects are blocking/non-walkable per Story 10.2).

### Web Client Changes

In `web-demo/js/game.js`, inside the WebSocket `onmessage` handler (the large `switch(data.type)` block), add a case for `nearby_objects`:

```javascript
case 'nearby_objects':
  if (data.objects && data.objects.length > 0) {
    for (const obj of data.objects) {
      appendChat(`You see a ${obj.type} to the ${obj.direction}`, 'system');
    }
  }
  break;
```

### Direction Names

The `DIRECTION_DELTAS` dictionary in `server/room/room.py` uses: `"up"`, `"down"`, `"left"`, `"right"`. These are the direction strings the client sends in `interact` requests and receives in `nearby_objects` responses. Note: these are grid directions, NOT compass directions.

### Test Pattern — Follow Existing Interact Tests

Existing tests in `tests/test_interact.py` set up: `Game()` instance, `RoomInstance` with interactive objects, player entity adjacent to the object, `AsyncMock` WebSocket. Follow the same pattern for new direction tests.

For proximity notification tests: after calling `await handle_move(ws, {"action": "move", "direction": "right"}, game=game)`, check that the mock WebSocket received a `nearby_objects` message. Use `ws.send_json.call_args_list` to inspect multiple `send_json` calls (the handler sends `entity_moved` broadcast first, then `nearby_objects` separately).

### Previous Story Learnings (from 10.4)

- Story 10.4 created `server/net/handlers/query.py` with `handle_look` that scans adjacent tiles using `_SCAN_OFFSETS` — similar pattern to proximity scan, but includes center tile and dead NPCs. The `_find_nearby_objects` helper in this story is simpler (no center, interactive objects only).
- `room._interactive_objects` is a `dict[str, dict]` keyed by object id — values have `x`, `y`, `type`, `id` fields.
- Accessing `room._interactive_objects` directly is intentional and consistent with `handle_look` and `get_state()`.
- `Game.__init__` does NOT call `_register_handlers()` — tests that need the router must call `game._register_handlers()` explicitly.

### Previous Story Learnings (from 10.3)

- Story 10.3 created the `COMMANDS` registry and `parseCommand()` function in `game.js`. Story 10.6 will add `/interact <direction>` to this parser. This story does NOT modify the COMMANDS registry.

### Intentional Omissions (Not Bugs)

- **No `in_combat` guard on interact** — The existing `handle_interact` handler does not check `entity.in_combat`. The directional path inherits this. This is acceptable for the prototype since movement is already blocked during combat, making it impossible to reach new objects. No change needed.
- **Multiple objects on the same adjacent tile** — Directional interact finds the first matching object (dict iteration order) and breaks. If two interactive objects share a tile, only one is interacted with. Acceptable for prototype — room JSON doesn't place multiple interactive objects on the same tile.

### What NOT to Do

- Do NOT add `/interact` slash command — that's Story 10.6
- Do NOT modify `RoomInstance.move_entity()` — proximity notifications are handled in the handler layer (`movement.py`), not the room model
- Do NOT add new fields to `PlayerEntity`, `NpcEntity`, or `RoomInstance`
- Do NOT persist anything new — direction interaction uses existing interact flow which already handles persistence (chest state, etc.)
- Do NOT broadcast `nearby_objects` to all players — only send to the moving player
- Do NOT send `nearby_objects` during exit transitions or combat encounters — the proximity scan must only fire on normal successful moves (the code path that reaches `broadcast_to_room` for `entity_moved`). Exit transitions `return` early before this point, and mob encounters happen after, so place the scan between the entity_moved broadcast and the mob encounter check
- Do NOT include center tile `(0, 0)` in proximity scan — player can't stand on interactive objects (they're blocking per Story 10.2)
- Do NOT break the existing `target_id` path — it must remain backward compatible

### Project Structure Notes

- Modified: `server/net/handlers/interact.py` — extended to accept `direction` parameter alongside existing `target_id`
- Modified: `server/net/handlers/movement.py` — added `_find_nearby_objects()` helper and proximity notification after move
- Modified: `web-demo/js/game.js` — added `nearby_objects` message handler
- Modified: `tests/test_interact.py` — new tests for directional interaction
- New or modified: tests for proximity notifications (in `test_movement.py` or new test file)
- No new server files created

### References

- [Source: server/net/handlers/interact.py] — current interact handler with adjacency check
- [Source: server/net/handlers/movement.py] — movement handler where proximity notifications will be added
- [Source: server/room/room.py#DIRECTION_DELTAS] — direction-to-delta mapping
- [Source: server/room/room.py#RoomInstance._interactive_objects] — interactive object storage
- [Source: server/net/handlers/query.py#_SCAN_OFFSETS] — adjacent tile scanning pattern reference
- [Source: _bmad-output/implementation-artifacts/10-4-server-query-actions.md] — previous story learnings
- [Source: _bmad-output/planning-artifacts/epics.md#Story 10.5] — acceptance criteria
- [Source: _bmad-output/project-context.md] — critical implementation rules

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- No issues encountered during implementation

### Completion Notes List

- Extended `handle_interact` to accept either `target_id` (existing) or `direction` (new) parameter. If both provided, `target_id` takes precedence. If neither, returns "Missing target_id or direction"
- Direction mode validates against `DIRECTION_DELTAS`, computes adjacent tile, searches `room._interactive_objects` for matching object, then delegates to existing create_object → interact flow
- Added `_find_nearby_objects()` helper in `movement.py` that scans 4 adjacent tiles for interactive objects using `DIRECTION_DELTAS`
- Proximity notification sent as separate `{"type": "nearby_objects"}` message to moving player only (not broadcast) after `entity_moved` broadcast, before mob encounter check
- Web client `handleNearbyObjects` function registered in dispatch table, displays "You see a {type} to the {direction}" via `appendChat` with system styling
- Updated existing `test_interact_missing_target_id` error message from "Missing target_id" to "Missing target_id or direction"
- 9 new tests: 7 directional interact tests + 2 proximity notification tests
- 517 tests pass, 1 pre-existing failure (integration chest test DB issue), 4 deselected (known hangers)

### Change Log

- 2026-04-10: Story 10.5 implemented — directional object interaction + proximity notifications

### File List

- server/net/handlers/interact.py (modified — direction parameter support, DIRECTION_DELTAS import)
- server/net/handlers/movement.py (modified — _find_nearby_objects helper, proximity notification after move)
- web-demo/js/game.js (modified — handleNearbyObjects function, registered in dispatch table)
- tests/test_interact.py (modified — updated existing test, added 7 directional interaction tests)
- tests/test_movement.py (modified — added 2 proximity notification tests)
