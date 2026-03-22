# Story 2.2: Static Room Objects

Status: done

## Story

As a player,
I want to see trees, rocks, and other terrain features in the room,
So that the world feels like a real environment with natural obstacles.

## Acceptance Criteria

1. Room JSON defines static objects in the `"objects"` array (e.g., `{"type": "rock", "x": 3, "y": 4, "category": "static", "blocking": true}`)
2. When a room is loaded, blocking static objects make their tiles non-walkable
3. The `room_state` message includes the objects list so clients can render them
4. Moving onto a tile with a blocking static object returns error: `"Tile not walkable"`
5. Decorative (non-blocking) static objects allow normal movement onto their tile

## Tasks / Subtasks

- [ ] Task 1: Update `RoomInstance.__init__` to process static objects (AC: #1, #2)
  - [ ] After building the grid, iterate `self.objects` for entries with `"category": "static"` and `"blocking": true`
  - [ ] For each blocking object, set `self._grid[y][x] = TileType.WALL` (overwrite tile to make it non-walkable)
  - [ ] Non-blocking objects (decorative) leave tiles unchanged
- [ ] Task 2: Update `RoomInstance.get_state()` to include objects (AC: #3)
  - [ ] Add `"objects": self.objects` to the returned dict
- [ ] Task 3: Update `data/rooms/test_room.json` with sample static objects (AC: #1)
  - [ ] Add a blocking rock and a non-blocking flower to the objects array
- [ ] Task 4: Write tests `tests/test_static_objects.py` (AC: #1-5)
  - [ ] Test blocking static object makes tile non-walkable
  - [ ] Test move onto blocking object returns "Tile not walkable"
  - [ ] Test decorative (non-blocking) object allows movement
  - [ ] Test room_state includes objects list
  - [ ] Test objects are included when room is loaded via RoomManager
- [ ] Task 5: Verify all tests pass
  - [ ] Run `pytest tests/test_static_objects.py -v`
  - [ ] Run `pytest tests/ -v` to verify no regressions (90 existing tests)

## Dev Notes

### Architecture Compliance

| Component | File Location |
|-----------|--------------|
| Static object processing | `server/room/room.py` → `RoomInstance.__init__()` |
| State serialization | `server/room/room.py` → `RoomInstance.get_state()` |
| Test room data | `data/rooms/test_room.json` |

### Object JSON Format

Per architecture.md Section 4.1, static objects are defined in room JSON:
```json
{
  "objects": [
    {"id": "rock_01", "type": "rock", "x": 3, "y": 4, "category": "static", "blocking": true},
    {"id": "tree_01", "type": "tree", "x": 1, "y": 3, "category": "static", "blocking": true},
    {"id": "flower_01", "type": "flower", "x": 2, "y": 1, "category": "static", "blocking": false}
  ]
}
```

### Implementation Approach

The simplest approach: during `RoomInstance.__init__`, after storing the grid, process the objects list. For blocking static objects, overwrite their tile to `TileType.WALL`. This way, the existing `move_entity()` walkability check handles blocking automatically — no changes needed to movement code.

```python
# In RoomInstance.__init__, after self._grid = tile_data:
for obj in self.objects:
    if obj.get("category") == "static" and obj.get("blocking", False):
        ox, oy = obj["x"], obj["y"]
        if 0 <= oy < self.height and 0 <= ox < self.width:
            self._grid[oy][ox] = TileType.WALL
```

### get_state() Change

Current `get_state()` returns: `room_key, name, width, height, tiles, entities, exits`
Add: `"objects": self.objects`

This sends the full objects list to the client for rendering (trees, rocks, flowers, etc.).

### Existing Movement — No Changes Needed

`move_entity()` already checks walkability via `is_walkable(tile_value)`. By setting blocking tiles to `TileType.WALL`, the existing logic returns `{"success": False, "reason": "wall"}` which `handle_move` maps to `"Tile not walkable"`. No handler changes required.

### Anti-Patterns to Avoid

- **DO NOT** create `server/room/objects/` subsystem — that's for interactive objects in Epic 3
- **DO NOT** create a RoomObject base class — not needed for static objects
- **DO NOT** modify `move_entity()` — tile overwrite makes it work automatically
- **DO NOT** modify movement handler — error mapping already handles "wall" reason
- **DO NOT** add object interaction — that's Story 3.1

### Previous Story Intelligence

From Story 2.1:
- Movement handler delegates to `room.move_entity()` and maps "wall" → "Tile not walkable"
- `RoomInstance.get_state()` is sent via `room_state` message on login
- 90 existing tests must not regress
- Test pattern: unit tests with mocked Game, RoomInstance constructed directly

### Project Structure Notes

- Modified files: `server/room/room.py`, `data/rooms/test_room.json`
- New files: `tests/test_static_objects.py`
- No new modules or classes needed

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#4.1 Object Categories]
- [Source: _bmad-output/planning-artifacts/architecture.md#4.2 State Scope]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.2]
- [Source: _bmad-output/implementation-artifacts/2-1-player-movement-and-collision.md#Dev Agent Record]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References
None

### Completion Notes List
- `RoomInstance.__init__` now processes static objects: blocking objects overwrite their tile to TileType.WALL
- `get_state()` now includes `"objects"` key in returned dict
- Only `category: "static"` objects with `blocking: true` are processed — interactive objects are ignored (Story 3.1)
- Bounds-checked: out-of-range object coordinates are safely skipped
- Updated `data/rooms/test_room.json` with sample rock (blocking) and flower (decorative)
- 8 new tests (98 total), all passing — blocking, decorative, get_state, RoomManager, edge cases

### File List
- `server/room/room.py` (modified) — Static object processing in __init__, objects in get_state()
- `data/rooms/test_room.json` (modified) — Added sample static objects
- `tests/test_static_objects.py` (new) — 8 static object tests
