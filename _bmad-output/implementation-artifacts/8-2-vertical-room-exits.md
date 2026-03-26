# Story 8.2: Vertical Room Exits

Status: done

## Story

As a player,
I want to climb stairs and descend ladders to reach rooms above or below,
so that the world has vertical depth beyond flat horizontal connections.

## Acceptance Criteria

1. **Given** the `TileType` enum exists with FLOOR=0, WALL=1, EXIT=2, MOB_SPAWN=3, WATER=4,
   **When** the story is complete,
   **Then** `STAIRS_UP=5` and `STAIRS_DOWN=6` are added to the enum,
   **And** both are added to `WALKABLE_TILES`.

2. **Given** a player walks onto a `STAIRS_UP` or `STAIRS_DOWN` tile,
   **When** `room.py:move_entity` processes the move,
   **Then** exit detection triggers for stairs tiles (same as EXIT tiles),
   **And** the exit info is returned in the move result.

3. **Given** room JSON `exits` array has entries for vertical exits,
   **When** the exit is configured,
   **Then** vertical exits use `"direction": "ascend"` or `"direction": "descend"` (NOT "up"/"down" which collide with movement direction strings).

4. **Given** movement direction strings are "up"/"down"/"left"/"right" (grid directions),
   **When** a vertical exit is processed,
   **Then** "ascend"/"descend" are used exclusively for exit metadata — no collision with movement input.

5. **Given** the client renders tiles,
   **When** a STAIRS_UP or STAIRS_DOWN tile is encountered,
   **Then** the tile type ID (5 or 6) is included in the room_state tiles grid for client rendering.

6. **Given** existing room JSON files use tile values 0-4,
   **When** the new tile types are added,
   **Then** no existing room data is affected (5 and 6 were not used previously).

7. **Given** existing tests assert `TileType` has specific values,
   **When** the story is complete,
   **Then** tile tests are updated to include STAIRS_UP and STAIRS_DOWN,
   **And** walkability tests verify both are walkable,
   **And** `pytest tests/` passes.

## Tasks / Subtasks

- [x] Task 1: Add new tile types (AC: 1)
  - [x] In `server/room/tile.py`: add `STAIRS_UP = 5` and `STAIRS_DOWN = 6` to `TileType` IntEnum
  - [x] Add both to `WALKABLE_TILES` frozenset

- [x] Task 2: Extend exit detection (AC: 2)
  - [x] In `server/room/room.py` `move_entity()`: change `if tile_value == TileType.EXIT:` to `if tile_value in (TileType.EXIT, TileType.STAIRS_UP, TileType.STAIRS_DOWN):`
  - [x] No changes to `_handle_exit_transition()` in movement.py — it's fully data-driven

- [x] Task 3: Update client tile rendering (AC: 5)
  - [x] In `web-demo/js/game.js` `tileClass()`: add `case 5: return 'tile-stairs-up';` and `case 6: return 'tile-stairs-down';`
  - [x] In `web-demo/css/style.css`: add `.tile-stairs-up` and `.tile-stairs-down` CSS rules
  - [x] Updated icon legend in `index.html` with Stairs Up and Stairs Down swatches

- [x] Task 4: Add sample vertical exits to room data (AC: 3, 4, 6)
  - [x] town_square: STAIRS_DOWN tile at (25,25) → dark_cave with direction "descend"
  - [x] dark_cave: STAIRS_UP tile at (25,25) → town_square with direction "ascend"
  - [x] Reciprocal exits confirmed

- [x] Task 5: Update tests (AC: 7)
  - [x] `test_tile_type_values()`: STAIRS_UP=5, STAIRS_DOWN=6
  - [x] `test_walkable_tiles()`: both walkable
  - [x] `test_is_walkable()`: values 5 and 6 return True
  - [x] Added `test_move_entity_stairs_up_exit_detection()`
  - [x] Added `test_move_entity_stairs_down_exit_detection()`
  - [x] Updated `test_sample_data.py`: exit count assertions changed to `>= 1`

## Dev Notes

### Key Architecture Patterns

- **Exit detection is tile-type-based**: `room.py` `move_entity()` checks `tile_value == TileType.EXIT` at line ~144. Stairs tiles need the same treatment — extend the condition.
- **Movement handler is data-driven**: `movement.py` `_handle_exit_transition()` reads `exit_info` dict fields (`target_room`, `entry_x`, `entry_y`) without caring about the tile type or direction. No handler changes needed.
- **Exit JSON `direction` field is descriptive only**: The server doesn't use `direction` for routing — it's metadata. Using `"ascend"`/`"descend"` avoids collision with movement input strings `"up"`/`"down"`/`"left"`/`"right"`.
- **Grid coordinates**: `grid[y][x]` — row-major. When placing stair tiles in JSON `tile_data`, index as `tile_data[y][x]`.

### Current Exit Detection Code (room.py ~line 144)

```python
if tile_value == TileType.EXIT:
    for exit_info in self.exits:
        if exit_info["x"] == nx and exit_info["y"] == ny:
            result["exit"] = exit_info
            break
```

Change the `if` to: `if tile_value in (TileType.EXIT, TileType.STAIRS_UP, TileType.STAIRS_DOWN):`

### Client Tile Rendering

Current `tileClass()` in `game.js` (~line 447) maps tile type integers to CSS classes. Unknown types fall through to `'tile-floor'`. Add two new cases.

CSS suggestions for stairs:
```css
.tile-stairs-up   { background: #3a2a1a; border: 1px solid #5a4a2a; }  /* warm brown — ascending */
.tile-stairs-down { background: #2a1a1a; border: 1px solid #4a2a2a; }  /* dark red-brown — descending */
```

### Room Data Format

Exit array entry format (existing pattern, no changes to schema):
```json
{
  "target_room": "dark_cave",
  "x": 25, "y": 25,
  "direction": "descend",
  "entry_x": 25, "entry_y": 25
}
```

The tile at `tile_data[25][25]` must be set to `6` (STAIRS_DOWN) for this exit to trigger.

### What NOT to Build

- No new room JSON files — reuse existing rooms with added stair tiles
- No new movement directions — "ascend"/"descend" are exit metadata, not player input actions
- No interact-based triggering — walking onto the tile triggers the transition (same as regular exits)
- No animation or transition effects in the client
- No floor/level numbering system

### Test Patterns

All tile/room tests in `test_room_system.py` use direct assertions:
```python
assert TileType.EXIT == 2
assert TileType.EXIT in WALKABLE_TILES
assert is_walkable(2) is True
```

Exit detection tests create a `Room` with known grid and exits, call `move_entity()`, and assert `result.get("exit")` is present.

### Project Structure Notes

- Server changes: `server/room/tile.py` (enum + walkability), `server/room/room.py` (exit detection condition)
- Client changes: `web-demo/js/game.js` (tileClass), `web-demo/css/style.css` (new tile styles), `web-demo/index.html` (legend update)
- Data changes: room JSON files in `data/rooms/`
- Tests: `tests/test_room_system.py`, potentially `tests/test_sample_data.py`
- No new files needed

### References

- [Source: server/room/tile.py — TileType enum, WALKABLE_TILES, is_walkable()]
- [Source: server/room/room.py#move_entity — exit detection at line ~144]
- [Source: server/net/handlers/movement.py#_handle_exit_transition — data-driven exit processing]
- [Source: data/rooms/town_square.json — exit array format reference]
- [Source: web-demo/js/game.js#tileClass — tile type to CSS class mapping]
- [Source: web-demo/css/style.css — tile CSS rules]
- [Source: tests/test_room_system.py — tile type values and walkability tests]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 8.2 — full acceptance criteria]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References

### Completion Notes List
- Task 1: Added STAIRS_UP=5, STAIRS_DOWN=6 to TileType enum and WALKABLE_TILES frozenset
- Task 2: Extended exit detection condition in room.py to include STAIRS_UP and STAIRS_DOWN
- Task 3: Added tile CSS classes, tileClass cases, and legend entries for both stair types
- Task 4: Added STAIRS_DOWN at (25,25) in town_square→dark_cave and STAIRS_UP at (25,25) in dark_cave→town_square
- Task 5: Updated 3 existing tile tests, added 2 new stair exit detection tests, fixed sample_data exit count assertions; 374 tests pass

### File List
- `server/room/tile.py` — Added STAIRS_UP=5, STAIRS_DOWN=6 to TileType, added to WALKABLE_TILES
- `server/room/room.py` — Extended exit detection to include STAIRS_UP and STAIRS_DOWN
- `web-demo/js/game.js` — Added case 5/6 to tileClass()
- `web-demo/css/style.css` — Added .tile-stairs-up and .tile-stairs-down styles
- `web-demo/index.html` — Added Stairs Up/Down to legend
- `data/rooms/town_square.json` — Added STAIRS_DOWN tile + descend exit
- `data/rooms/dark_cave.json` — Added STAIRS_UP tile + ascend exit
- `tests/test_room_system.py` — Updated tile tests, added stair exit detection tests
- `tests/test_sample_data.py` — Updated exit count assertions
