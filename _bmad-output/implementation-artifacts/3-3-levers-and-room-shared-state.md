# Story 3.3: Levers & Room-Shared State

Status: done

## Story

As a player,
I want to pull levers that change the room for everyone,
So that I can solve environmental puzzles and open paths.

## Acceptance Criteria

1. Player interacts with a lever with config `{"target": "gate_1", "action": "toggle"}` → the target tile toggles between wall and floor
2. Lever state is persisted to `RoomState.dynamic_state` (room-scoped, shared across all players)
3. All players in the room receive a state update with the changed tile
4. Client receives `interact_result` confirming the action
5. Lever already toggled to "on" → interacting again toggles back to "off" and reverts the target tile

## Tasks / Subtasks

- [ ] Task 1: Create `server/room/objects/lever.py` with `LeverObject` class (AC: #1, #2, #4, #5)
  - [ ] Subclass `InteractiveObject`
  - [ ] Override `async def interact(player_id, game) -> dict`
  - [ ] Load room state via `get_room_object_state(session, room_key, object_id)`
  - [ ] Toggle `active` boolean in state
  - [ ] Get target tile coords from `self.config["target_x"]`, `self.config["target_y"]`
  - [ ] Toggle target tile between `TileType.WALL` and `TileType.FLOOR` in `RoomInstance._grid`
  - [ ] Save state via `set_room_object_state()`
  - [ ] Return `{"status": "toggled", "active": bool, "target_x": int, "target_y": int}`
- [ ] Task 2: Broadcast tile change to all room players (AC: #3)
  - [ ] After toggling, call `game.connection_manager.broadcast_to_room()` with `{"type": "tile_changed", "x": target_x, "y": target_y, "tile_type": new_tile}`
- [ ] Task 3: Register `LeverObject` in `server/room/objects/__init__.py` (AC: #1)
  - [ ] `register_object_type("lever", LeverObject)`
- [ ] Task 4: Write tests `tests/test_lever.py` (AC: #1-5)
  - [ ] Test lever toggles target tile from wall to floor
  - [ ] Test lever toggles back from floor to wall
  - [ ] Test lever state persisted to room-scoped state
  - [ ] Test all players in room receive tile_changed broadcast
  - [ ] Test interact_result confirms toggle
- [ ] Task 5: Verify all tests pass
  - [ ] Run `pytest tests/test_lever.py -v`
  - [ ] Run `pytest tests/ -v` to verify no regressions (136 existing tests)

## Dev Notes

### Architecture Compliance

| Component | File Location |
|-----------|--------------|
| LeverObject class | `server/room/objects/lever.py` |
| Object registration | `server/room/objects/__init__.py` |

### Lever JSON Format

```json
{
  "id": "lever_01",
  "type": "lever",
  "category": "interactive",
  "x": 2, "y": 0,
  "state_scope": "room",
  "config": {
    "target_x": 3, "target_y": 2,
    "action": "toggle"
  }
}
```

### Tile Change Broadcast

```python
{"type": "tile_changed", "x": 3, "y": 2, "tile_type": 0}  # 0=FLOOR, 1=WALL
```

### Existing Infrastructure to Reuse

- **InteractiveObject base**: `server/room/objects/base.py`
- **Room-scoped state**: `server/room/objects/state.py` — `get_room_object_state()` / `set_room_object_state()`
- **TileType**: `server/room/tile.py` — `TileType.FLOOR` (0) and `TileType.WALL` (1)
- **RoomInstance._grid**: Direct grid mutation `room._grid[y][x] = tile_value`
- **broadcast_to_room**: `game.connection_manager.broadcast_to_room(room_key, msg)`
- **Lever needs access to room**: Use `game.room_manager.get_room(room_key)` to get room instance

### Anti-Patterns to Avoid

- **DO NOT** implement complex puzzle mechanics — just toggle wall/floor
- **DO NOT** add lever cooldowns or activation delays
- **DO NOT** chain levers (one lever triggering another)
- **DO** persist state so levers survive server restarts (via RoomState.dynamic_state)

### Previous Story Intelligence

From Story 3.2:
- `ChestObject` pattern: subclass InteractiveObject, override interact(), use state helpers
- `_get_room_key(game)` helper to find which room the object is in
- Registration via `server/room/objects/__init__.py`
- `async_session` for DB operations inside `interact()`
- 136 existing tests must not regress

### Project Structure Notes

- New files: `server/room/objects/lever.py`, `tests/test_lever.py`
- Modified files: `server/room/objects/__init__.py` (register lever type)

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#4.2 State Scope]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.3]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References
None

### Completion Notes List
- `server/room/objects/lever.py`: LeverObject toggles target tile between WALL/FLOOR, persists to room-scoped state, broadcasts tile_changed
- Registered "lever" type in `server/room/objects/__init__.py`
- 5 new tests (141 total), all passing — wall-to-floor toggle, floor-to-wall toggle, broadcast, result format, registration

### File List
- `server/room/objects/lever.py` (new) — Lever interactive object with tile toggle
- `server/room/objects/__init__.py` (modified) — Registered lever type
- `tests/test_lever.py` (new) — 5 lever interaction tests
