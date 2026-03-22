# Story 1.4: Tile System & Room Instance

Status: done

## Story

As a developer,
I want the tile type system and room instance class,
So that rooms can represent a 100x100 grid with entities and movement validation.

## Acceptance Criteria

1. `server/room/tile.py` defines TileType enum (floor, wall, exit, mob_spawn, water) with walkability rules
2. `WALKABLE_TILES` contains floor, exit, mob_spawn
3. `server/room/room.py` provides a RoomInstance class that builds a tile grid from 2D tile data
4. RoomInstance supports `add_entity`, `remove_entity`, `get_entities_at`, `get_player_spawn`, `get_player_ids`
5. `RoomInstance.move_entity` validates direction, checks bounds, checks walkability, returns result dict
6. `RoomInstance.move_entity` returns exit info when stepping on exit tile
7. `RoomInstance.move_entity` returns mob_encounter when stepping on a tile with an alive hostile mob
8. `RoomInstance.get_state` returns a serializable snapshot of room_key, name, dimensions, tiles, entities, exits
9. `server/player/entity.py` defines PlayerEntity dataclass with id, name, x, y, player_db_id, stats, in_combat flag
10. `server/room/manager.py` provides RoomManager with get_room, load_room, unload_room, transfer_entity methods

## Tasks / Subtasks

- [x] Task 1: Create `server/room/tile.py` (AC: #1, #2)
  - [x] Define `TileType` IntEnum: FLOOR=0, WALL=1, EXIT=2, MOB_SPAWN=3, WATER=4
  - [x] Define `WALKABLE_TILES` as a frozenset containing FLOOR, EXIT, MOB_SPAWN
  - [x] Add helper `is_walkable(tile_type: int) -> bool`
- [x] Task 2: Create `server/player/entity.py` (AC: #9)
  - [x] Define `PlayerEntity` dataclass with fields: id (str), name (str), x (int), y (int), player_db_id (int), stats (dict), in_combat (bool, default=False)
  - [x] `id` is a string entity ID (e.g., "player_1"), distinct from player_db_id (the DB primary key)
- [x] Task 3: Create `server/room/room.py` (AC: #3, #4, #5, #6, #7, #8)
  - [x] Define `RoomInstance` class initialized from room_key, name, width, height, tile_data (2D list), exits (list), objects (list), spawn_points (list)
  - [x] Build internal `_grid: list[list[int]]` from tile_data
  - [x] Track entities in a dict `_entities: dict[str, PlayerEntity]` keyed by entity id
  - [x] Implement `add_entity(entity: PlayerEntity)` — stores entity in dict
  - [x] Implement `remove_entity(entity_id: str) -> PlayerEntity | None`
  - [x] Implement `get_entities_at(x: int, y: int) -> list[PlayerEntity]`
  - [x] Implement `get_player_spawn() -> tuple[int, int]` — returns first spawn_point with type="player", fallback to (0,0)
  - [x] Implement `get_player_ids() -> list[str]` — returns all entity IDs
  - [x] Implement `move_entity(entity_id, direction) -> dict` with keys: success, x, y, exit (optional), mob_encounter (optional)
    - [x] Validate direction is one of "up", "down", "left", "right"
    - [x] Calculate new position from direction (up: y-1, down: y+1, left: x-1, right: x+1)
    - [x] Check bounds (0 <= x < width, 0 <= y < height)
    - [x] Check walkability using `tile.is_walkable()`
    - [x] If tile is EXIT, include exit info from exits list matching (x, y)
    - [x] If tile has a hostile mob entity, include mob_encounter info
    - [x] Update entity position on success
  - [x] Implement `get_state() -> dict` returning room_key, name, width, height, tiles (2D list), entities (list of entity dicts), exits
- [x] Task 4: Create `server/room/manager.py` (AC: #10)
  - [x] Define `RoomManager` class with `_rooms: dict[str, RoomInstance]`
  - [x] Implement `get_room(room_key: str) -> RoomInstance | None`
  - [x] Implement `load_room(room_db: Room) -> RoomInstance` — creates RoomInstance from DB Room model
  - [x] Implement `unload_room(room_key: str) -> None`
  - [x] Implement `transfer_entity(entity: PlayerEntity, from_room_key: str, to_room_key: str) -> RoomInstance | None`
    - [x] Remove entity from source room
    - [x] Get target room, place entity at player spawn point
    - [x] Return target RoomInstance or None if target not loaded
- [x] Task 5: Write tests `tests/test_room_system.py`
  - [x] Test TileType enum values and WALKABLE_TILES
  - [x] Test PlayerEntity creation and defaults
  - [x] Test RoomInstance: add/remove/get entities, get_player_spawn, get_player_ids
  - [x] Test RoomInstance.move_entity: valid move, wall blocked, bounds blocked, exit detection
  - [x] Test RoomInstance.get_state serialization
  - [x] Test RoomManager: load_room, get_room, unload_room, transfer_entity
- [x] Task 6: Verify all tests pass
  - [x] Run `pytest tests/test_room_system.py -v`
  - [x] Run `pytest tests/ -v` to verify no regressions

## Dev Notes

### Architecture Compliance

| Component | File Location |
|-----------|--------------|
| TileType enum, walkability | `server/room/tile.py` |
| PlayerEntity dataclass | `server/player/entity.py` |
| RoomInstance (grid, entities, movement) | `server/room/room.py` |
| RoomManager (active rooms) | `server/room/manager.py` |

### TileType Integer Mapping

Tile types are stored as integers in the JSON tile_data grid. The mapping:

| Integer | TileType | Walkable |
|---------|----------|----------|
| 0 | FLOOR | Yes |
| 1 | WALL | No |
| 2 | EXIT | Yes |
| 3 | MOB_SPAWN | Yes |
| 4 | WATER | No |

The existing `data/rooms/test_room.json` already uses this encoding (0=floor, 2=exit at position [4,4]).

### Direction-to-Delta Mapping

```python
DIRECTION_DELTAS = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}
```

Note: `tile_data[y][x]` — row-major order (y is the outer index, x is inner).

### move_entity Return Format

```python
# Success:
{"success": True, "x": 5, "y": 3}

# Success with exit:
{"success": True, "x": 9, "y": 5, "exit": {"target_room": "dark_cave", "x": 9, "y": 5, "direction": "east"}}

# Success with mob encounter:
{"success": True, "x": 3, "y": 7, "mob_encounter": {"entity_id": "mob_goblin_1", "name": "Goblin"}}

# Failure:
{"success": False, "reason": "wall"}  # or "bounds" or "invalid_direction"
```

### Exit Matching

Exits are stored in the room's `exits` list (from JSON). When a player steps on an EXIT tile, find the matching exit entry by (x, y) coordinates:

```python
exit_info = next((e for e in self.exits if e["x"] == nx and e["y"] == ny), None)
```

### Mob Encounter Detection

For Story 1.4, mob encounter detection checks if any entity at the target tile is a "mob" type. Since NPC/mob entities are not yet implemented (Story 3.4+), for now just check if any non-player entity exists at the target. The mob_encounter key is included in the result but actual combat triggering is a later story.

A simple approach: track a separate `_mob_entities` dict or check entity ID prefixes. For now, the test can use a simple mock approach — add a PlayerEntity with a special flag or just test the exit path. Full mob encounter testing comes in Epic 3.

### RoomInstance vs Room (DB Model)

- `Room` (in `server/room/models.py`) is the **SQLAlchemy DB model** — persistence layer
- `RoomInstance` (in `server/room/room.py`) is the **runtime class** — holds the live grid, entities, handles movement

`RoomManager.load_room()` converts a DB `Room` model into a `RoomInstance`.

### RoomManager.transfer_entity Flow

1. Remove entity from source room (`source_room.remove_entity(entity.id)`)
2. Get target room (`self.get_room(to_room_key)`)
3. If target exists: set entity position to target's player spawn, add to target room
4. Return target RoomInstance or None

### Existing Code to Use

- `from server.room.models import Room` — DB model (room_key, name, width, height, tile_data, exits, objects, spawn_points)
- `from server.player.models import Player` — DB model (for reference, not used directly in this story)
- `from server.room import repo as room_repo` — get_by_key, upsert_room
- `from server.room.provider import JsonRoomProvider` — loads rooms from JSON
- Test fixture pattern from `tests/test_repos.py` — in-memory SQLite, import models, Base.metadata.create_all

### Anti-Patterns to Avoid

- **DO NOT** name the class `Room` — use `RoomInstance` to avoid collision with the `Room` DB model in `server/room/models.py`
- **DO NOT** create WebSocket handlers, combat logic, or NPC spawning — those are later stories
- **DO NOT** create room objects (chests, levers, NPCs) — that's Epic 3
- **DO NOT** import or use the DB session in RoomInstance — it's a pure in-memory runtime class
- **DO NOT** persist entity positions from RoomInstance — that's handled by repos in other stories

### Previous Story Intelligence

From Story 1.3:
- Repos use stateless async functions with session-as-parameter
- JsonRoomProvider loads .json from data/rooms/ and upserts via room_repo
- test_room.json: 5x5 grid, tile values 0 (floor) and 2 (exit at [4,4]), exit to "other_room", player spawn at (2,2)
- 11 existing tests must not regress

### Project Structure Notes

- New files: `room/tile.py`, `room/room.py`, `room/manager.py`, `player/entity.py`, `tests/test_room_system.py`
- All target `__init__.py` files already exist
- RoomInstance is a pure Python class — no DB dependencies, no async, easy to test

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#2.2 Tile Grid]
- [Source: _bmad-output/planning-artifacts/architecture.md#2.3 Entities]
- [Source: _bmad-output/planning-artifacts/architecture.md#3.1 Directory Structure]
- [Source: _bmad-output/planning-artifacts/architecture.md#4. Room Object System]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.4]
- [Source: _bmad-output/implementation-artifacts/1-3-persistence-repositories.md#Dev Agent Record]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References
None

### Completion Notes List
- TileType is an IntEnum matching JSON tile_data integer encoding (0=floor, 1=wall, 2=exit, 3=mob_spawn, 4=water)
- PlayerEntity is a pure dataclass with string entity ID (distinct from DB primary key)
- RoomInstance is a pure Python class — no DB or async dependencies, easy to test
- Movement uses row-major grid access: `_grid[y][x]`
- Mob encounter detection uses entity ID prefix "mob_" convention
- RoomManager.load_room converts DB Room model → RoomInstance
- RoomManager.transfer_entity handles spawn point placement in target room
- 22 new tests (33 total), all passing

### File List
- `server/room/tile.py` (new) — TileType enum, WALKABLE_TILES, is_walkable()
- `server/player/entity.py` (new) — PlayerEntity dataclass
- `server/room/room.py` (new) — RoomInstance class with grid, entities, movement
- `server/room/manager.py` (new) — RoomManager for active room tracking
- `tests/test_room_system.py` (new) — 22 tests for tile/entity/room/manager
