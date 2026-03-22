# Story 2.3: Room Transitions via Exit Tiles

Status: done

## Story

As a player,
I want to walk onto an exit tile and be transported to another room,
So that I can explore the larger world across multiple zones.

## Acceptance Criteria

1. When a player moves onto an exit tile, they are removed from the current room
2. Other players in the old room receive an `entity_left` message
3. The player is placed in the target room at the configured entry coordinates (or player spawn)
4. The player receives a `room_state` message with the new room's full data
5. Other players in the new room receive an `entity_entered` message
6. The player's `current_room_id` and position are saved to the database
7. If the exit target room doesn't exist, the client receives error: `"Exit leads nowhere"` and position doesn't change

## Tasks / Subtasks

- [ ] Task 1: Extend `handle_move` to detect and handle exit transitions (AC: #1-6)
  - [ ] After successful move, check `result.get("exit")` for exit info
  - [ ] If exit present: perform room transition (extract target_room, entry_x, entry_y from exit info)
  - [ ] Load target room from `game.room_manager` (or from DB via `room_repo` if not loaded)
  - [ ] Remove entity from current room via `room.remove_entity(entity_id)`
  - [ ] Broadcast `entity_left` to old room (AC: #2)
  - [ ] Update entity position to entry coordinates (use exit's `entry_x/entry_y` if present, else room's player spawn)
  - [ ] Add entity to target room via `target_room.add_entity(entity)`
  - [ ] Update `game.player_entities[entity_id]["room_key"]` to new room
  - [ ] Update `game.connection_manager.update_room(entity_id, new_room_key)`
  - [ ] Send `room_state` to the transitioning player (AC: #4)
  - [ ] Broadcast `entity_entered` to new room, excluding the transitioning player (AC: #5)
  - [ ] Save position to DB via `player_repo.update_position()` (AC: #6)
- [ ] Task 2: Handle "exit leads nowhere" error (AC: #7)
  - [ ] If target room not in memory and not in DB, revert the player's position
  - [ ] Send error: `"Exit leads nowhere"`
  - [ ] Critical: must revert entity position since `move_entity()` already moved them
- [ ] Task 3: Create a second test room `data/rooms/other_room.json` for transition testing
  - [ ] Simple 5x5 room with an exit back to `test_room`
  - [ ] Player spawn at (1, 1)
- [ ] Task 4: Write tests `tests/test_room_transition.py` (AC: #1-7)
  - [ ] Test successful room transition: entity removed from old room, added to new room
  - [ ] Test entity_left broadcast to old room
  - [ ] Test room_state sent to transitioning player
  - [ ] Test entity_entered broadcast to new room
  - [ ] Test player position updated to entry coordinates
  - [ ] Test player_entities and connection_manager room_key updated
  - [ ] Test position saved to DB
  - [ ] Test exit leads nowhere returns error and position reverted
- [ ] Task 5: Verify all tests pass
  - [ ] Run `pytest tests/test_room_transition.py -v`
  - [ ] Run `pytest tests/ -v` to verify no regressions (98 existing tests)

## Dev Notes

### Architecture Compliance

| Component | File Location |
|-----------|--------------|
| Transition logic | `server/net/handlers/movement.py` → `handle_move` (extend) |
| Room transfer | `server/room/manager.py` → `RoomManager` (existing) |
| Connection update | `server/net/connection_manager.py` → `update_room()` (existing) |
| Position save | `server/player/repo.py` → `update_position()` (existing) |

### Exit Info Format

`room.move_entity()` returns exit info when stepping on an EXIT tile:
```python
{"success": True, "x": 4, "y": 4, "exit": {"target_room": "other_room", "x": 4, "y": 4, "direction": "east"}}
```

The exit dict comes from the room JSON. It may optionally have `entry_x` and `entry_y` for the target room entry point. If not present, use the target room's player spawn point.

### Transition Flow

```python
exit_info = result.get("exit")
if exit_info:
    target_room_key = exit_info["target_room"]

    # Load target room
    target_room = game.room_manager.get_room(target_room_key)
    if target_room is None:
        # Try loading from DB
        async with async_session() as session:
            room_db = await room_repo.get_by_key(session, target_room_key)
            if room_db is None:
                # Revert position and send error
                entity.x, entity.y = old_x, old_y
                await websocket.send_json({"type": "error", "detail": "Exit leads nowhere"})
                return
            target_room = game.room_manager.load_room(room_db)

    # Remove from current room
    room.remove_entity(entity_id)
    await game.connection_manager.broadcast_to_room(
        room_key, {"type": "entity_left", "entity_id": entity_id}, exclude=entity_id
    )

    # Place in new room
    entry_x = exit_info.get("entry_x")
    entry_y = exit_info.get("entry_y")
    if entry_x is None or entry_y is None:
        entry_x, entry_y = target_room.get_player_spawn()
    entity.x = entry_x
    entity.y = entry_y
    target_room.add_entity(entity)

    # Update tracking
    game.player_entities[entity_id]["room_key"] = target_room_key
    game.connection_manager.update_room(entity_id, target_room_key)

    # Save to DB
    async with async_session() as session:
        await player_repo.update_position(session, entity.player_db_id, target_room_key, entry_x, entry_y)

    # Send new room state
    await websocket.send_json({"type": "room_state", **target_room.get_state()})

    # Notify new room
    entity_data = {"id": entity.id, "name": entity.name, "x": entity.x, "y": entity.y}
    await game.connection_manager.broadcast_to_room(
        target_room_key, {"type": "entity_entered", "entity": entity_data}, exclude=entity_id
    )
    return  # Don't broadcast entity_moved for the old room
```

### Position Revert on Error

Important: `move_entity()` already updated the entity's x/y before returning the result. If the exit target doesn't exist, we must revert:
```python
old_x, old_y = entity.x, entity.y  # Save BEFORE move_entity...
```
Actually, save the old position before calling `move_entity()`, so it's available for revert.

### Existing Code to Reuse

- `ConnectionManager.update_room(entity_id, room_key)` — already exists
- `RoomManager.get_room(room_key)` — returns RoomInstance or None
- `RoomManager.load_room(room_db)` — creates RoomInstance from DB model
- `room_repo.get_by_key(session, room_key)` — looks up Room in DB
- `player_repo.update_position(session, player_id, room_key, x, y)` — saves position
- `room.get_player_spawn()` — returns (x, y) tuple

### Anti-Patterns to Avoid

- **DO NOT** use `RoomManager.transfer_entity()` directly — it doesn't handle broadcasting, DB saves, or connection updates. Implement the full flow in the handler.
- **DO NOT** broadcast entity_moved when an exit transition occurs — the player leaves the room
- **DO NOT** create a separate transition handler — keep it in handle_move where exit detection naturally occurs
- **DO NOT** forget to save old position before calling move_entity for revert capability

### Previous Story Intelligence

From Story 2.1:
- `handle_move` calls `room.move_entity()` and broadcasts `entity_moved` on success
- Need to add exit check AFTER successful move but BEFORE broadcasting entity_moved
- Handler has access to `game.connection_manager`, `game.room_manager`, `game.player_entities`

From Story 1.7 (login handler):
- Pattern for loading rooms from DB: `room_repo.get_by_key + game.room_manager.load_room`
- Pattern for sending room_state: `await websocket.send_json({"type": "room_state", **room.get_state()})`
- Pattern for entity_entered broadcast

### Project Structure Notes

- Modified files: `server/net/handlers/movement.py`
- New files: `data/rooms/other_room.json`, `tests/test_room_transition.py`

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#8.3 Server Messages — entity_left, entity_entered, room_state]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.3]
- [Source: _bmad-output/implementation-artifacts/2-1-player-movement-and-collision.md#Dev Agent Record]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References
None

### Completion Notes List
- Extended `handle_move` to detect exit transitions after successful move
- `_handle_exit_transition()` helper: loads target room (memory or DB), removes from old room, broadcasts entity_left, places in new room at entry coords, updates tracking, saves position to DB, sends room_state, broadcasts entity_entered
- Position revert on "exit leads nowhere": saves old_x/old_y before move_entity, reverts if target room not found
- Uses `exit_info.get("entry_x")` / `entry_y` for entry position, falls back to target room's player spawn
- Created `data/rooms/other_room.json` (5x5, exit back to test_room)
- 9 new tests (107 total), all passing — covers transition, entry coords, spawn fallback, room_state, tracking, DB save, entity_left/entered broadcasts, leads-nowhere error

### File List
- `server/net/handlers/movement.py` (modified) — Added exit transition handling with _handle_exit_transition helper
- `data/rooms/other_room.json` (new) — Second test room with exit back to test_room
- `tests/test_room_transition.py` (new) — 9 room transition tests
