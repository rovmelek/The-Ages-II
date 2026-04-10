# Story 10.2: Non-Walkable Interactive Objects

Status: done

## Story

As a player,
I want interactive objects (chests, levers) to block movement like obstacles,
so that I must stand next to them and interact deliberately, matching real game engine conventions.

## Acceptance Criteria

1. **Given** a room JSON defines a chest with `category: "interactive"` and `blocking: true`, **When** the room is loaded, **Then** the tile at the object's position is marked as non-walkable and the object is visible in room_state.

2. **Given** a player attempts to move onto a tile occupied by a blocking interactive object, **When** the server processes the move, **Then** the move is rejected with error "Tile not walkable" and position unchanged.

3. **Given** a player is adjacent to an interactive object (Manhattan distance = 1), **When** the player sends `{"action": "interact", "target_id": "chest_01"}`, **Then** the interaction succeeds.

4. **Given** a player is NOT adjacent to an interactive object (Manhattan distance > 1), **When** the player sends an interact action for that object, **Then** the client receives error: "Too far to interact".

5. **Given** existing interact tests assume no distance check, **When** the story is complete, **Then** all affected tests are updated to place the player adjacent to the object before interacting, and `pytest tests/` passes with no failures.

## Tasks / Subtasks

- [x] Task 1: Make interactive objects block tiles (AC: #1, #2)
  - [x] 1.1: In `server/room/room.py` `__init__`, change the blocking condition from `category == "static" and blocking` to just `blocking` — this makes ANY object with `"blocking": true` stamp `TileType.WALL` on the grid, regardless of category
  - [x] 1.2: Add `"blocking": true` to all interactive objects in room JSON files:
    - `data/rooms/town_square.json`: chest_01, chest_02, lever_01
    - `data/rooms/dark_cave.json`: chest_01, chest_02
    - `data/rooms/test_room.json`: chest_01
- [x] Task 2: Add adjacency check to interact handler (AC: #3, #4)
  - [x] 2.1: In `server/net/handlers/interact.py`, after looking up the object (after `room.get_object(target_id)`), get the player entity from `player_info["entity"]` and the object position from `obj_dict["x"]`, `obj_dict["y"]`. Compute Manhattan distance: `abs(entity.x - obj_x) + abs(entity.y - obj_y)`. If distance > 1, return error "Too far to interact". Distance 0 is allowed (edge case: player placed on object tile before blocking was applied).
  - [x] 2.2: The adjacency check must run BEFORE `create_object()` (the typed object construction) — no need to construct the object just to reject it
- [x] Task 3: Update existing tests (AC: #5)
  - [x] 3.1: In `tests/test_integration.py`, update the `room_manager` fixture — move the chest to position `(1, 0)` (adjacent to spawn `(0, 0)`) and add `"blocking": true`
  - [x] 3.2: Update `test_loot_chest` and `test_chest_already_looted` if they need any position changes beyond the fixture fix
  - [x] 3.3: Verify `test_interact_nonexistent_object` still passes (tests missing object_id, fails before adjacency check)
  - [x] 3.4: In `tests/test_interact.py`, move the test object to `(1, 0)` or `(0, 1)` (adjacent to player at `(0, 0)`) — current position `(1, 1)` has Manhattan distance 2, which will fail the adjacency check
  - [x] 3.5: In `tests/test_chest.py`, move the chest from `(2, 1)` to `(1, 0)` or `(0, 1)` (adjacent to player at `(0, 0)`) — affects 4+ handler tests
  - [x] 3.6: In `tests/test_static_objects.py`, update `test_non_static_objects_ignored` — it currently asserts that an interactive object with `blocking: true` does NOT affect the grid (`== TileType.FLOOR`). After the change, it SHOULD affect the grid (`== TileType.WALL`). Rename the test to `test_blocking_interactive_objects_affect_grid` and update the assertion
- [x] Task 4: New tests (AC: #1, #2, #3, #4)
  - [x] 4.1: Test that a blocking interactive object makes its tile non-walkable (movement blocked)
  - [x] 4.2: Test that interact succeeds when player is adjacent (Manhattan distance = 1)
  - [x] 4.3: Test that interact fails with "Too far to interact" when player is distant
  - [x] 4.4: Test that non-blocking interactive objects (if any exist) remain walkable
  - [x] 4.5: Run full test suite — `pytest tests/` must pass with no regressions

## Dev Notes

### Implementation Pattern

**Blocking condition change** (simplest approach): In `room.py` `__init__` line 52, the current condition is:
```python
if obj.get("category") == "static" and obj.get("blocking", False):
```
Change to:
```python
if obj.get("blocking", False):
```
This naturally handles both static and interactive objects. The `fountain_01` in town_square has `"blocking": false` and remains correctly walkable (non-blocking). Non-blocking static objects (if any) also work correctly.

**Adjacency check**: Use Manhattan distance (`abs(dx) + abs(dy)`), not Chebyshev. The game has 4-directional movement only (no diagonals), so Manhattan distance matches the movement model. `DIRECTION_DELTAS` in room.py confirms: `{"up": (0,-1), "down": (0,1), "left": (-1,0), "right": (1,0)}`.

**Distance = 0**: Allow it. If a player is somehow on the same tile as an interactive object (e.g., placed before blocking was applied, or in tests with manual placement), they should be able to interact. The `> 1` check naturally handles this.

### Interact Handler — Where to Add the Check

In `server/net/handlers/interact.py`, the adjacency check goes after the object lookup and before `create_object()`:

```python
obj_dict = room.get_object(target_id)
if obj_dict is None:
    # existing error handling
    return

# NEW: Adjacency check
entity = player_info["entity"]
obj_x, obj_y = obj_dict["x"], obj_dict["y"]
if abs(entity.x - obj_x) + abs(entity.y - obj_y) > 1:
    await websocket.send_json({"type": "error", "detail": "Too far to interact"})
    return

# existing: create_object and interact
```

`player_info` is already available from `game.player_entities.get(entity_id)` earlier in the handler.

### Room JSON Changes

All interactive objects need `"blocking": true` added. Example:
```json
{"id": "chest_01", "type": "chest", "x": 25, "y": 30, "category": "interactive", "blocking": true, ...}
```

6 objects across 3 room files need this field added.

### Test Fixture Fix

The `room_manager` fixture in `tests/test_integration.py` creates a chest at `(3, 3)` with spawn at `(0, 0)`. After adding the adjacency check, the player (at spawn) can't interact (Manhattan distance = 6). Move the chest to `(1, 0)` — adjacent to spawn. Also add `"blocking": true` to the fixture to match the new data convention.

### Previous Story Learnings (from 10.1)

- Use `new_callable=AsyncMock` when patching `player_repo`
- Mock `async_session` with `__aenter__`/`__aexit__` setup
- PlayerEntity needs explicit `stats={"hp": 100, ...}` in tests (defaults to empty dict)
- NPCs use `room.add_npc()` not `room.add_entity()`
- CombatManager uses `_player_to_instance` and `_instances` (not `_player_instances`)

### References

- [Source: server/room/room.py#__init__] — blocking object grid stamping (lines 51-56)
- [Source: server/room/room.py#_interactive_objects] — interactive object indexing (lines 46-49)
- [Source: server/net/handlers/interact.py] — interact handler (lines 16-59)
- [Source: server/room/tile.py] — TileType enum and WALKABLE_TILES
- [Source: tests/test_integration.py#TestChestInteraction] — existing interact tests (lines 227-256)
- [Source: data/rooms/town_square.json] — chest_01, chest_02, lever_01 objects
- [Source: _bmad-output/planning-artifacts/epics.md#Story 10.2] — acceptance criteria

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Completion Notes List

- Changed blocking condition from `category == "static" and blocking` to just `blocking`
- Added Manhattan distance adjacency check (distance > 1 rejected) in interact handler
- Added `blocking: true` to 6 interactive objects across 3 room JSON files
- Fixed 4 test files with position adjustments for adjacency compliance
- Renamed `test_non_static_objects_ignored` to `test_blocking_interactive_objects_affect_grid`
- 6 new tests in test_blocking_objects.py

### Change Log

- 2026-04-10: Story 10.2 implemented

### File List

- server/room/room.py (modified — blocking condition generalized)
- server/net/handlers/interact.py (modified — adjacency check added)
- data/rooms/town_square.json (modified — blocking:true on 3 interactive objects)
- data/rooms/dark_cave.json (modified — blocking:true on 2 interactive objects)
- data/rooms/test_room.json (modified — blocking:true on 1 interactive object)
- tests/test_interact.py (modified — object position fixed)
- tests/test_chest.py (modified — chest position fixed)
- tests/test_static_objects.py (modified — test renamed and assertion flipped)
- tests/test_integration.py (modified — chest position + movement steps added)
- tests/test_blocking_objects.py (new — 6 tests)
