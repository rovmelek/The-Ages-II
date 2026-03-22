# Story 2.1: Player Movement & Collision

Status: done

## Story

As a player,
I want to move in four directions on the tile grid and be blocked by walls and obstacles,
So that I can explore the room within its boundaries.

## Acceptance Criteria

1. Client sends `{"action": "move", "direction": "right"}` and player position updates to (x+1, y)
2. All players in the room receive `{"type": "entity_moved", "entity_id": "player_1", "x": 6, "y": 5}`
3. Moving into a wall tile returns error: `"Tile not walkable"`
4. Moving out of bounds returns error: `"Out of bounds"`
5. Invalid direction (e.g., "northwest") returns error: `"Invalid direction: northwest"`
6. Player in combat cannot move: `"Cannot move while in combat"`
7. Player not logged in cannot move: `"Not logged in"`

## Tasks / Subtasks

- [ ] Task 1: Create `server/net/handlers/movement.py` with `handle_move` (AC: #1-7)
  - [ ] Define `async def handle_move(websocket: WebSocket, data: dict, *, game: Game) -> None`
  - [ ] Look up entity_id via `game.connection_manager.get_entity_id(websocket)` — if None, send "Not logged in" error (AC: #7)
  - [ ] Look up player info from `game.player_entities[entity_id]` — get entity and room_key
  - [ ] Check `entity.in_combat` — if True, send "Cannot move while in combat" error (AC: #6)
  - [ ] Get room from `game.room_manager.get_room(room_key)`
  - [ ] Call `room.move_entity(entity_id, direction)` — returns result dict
  - [ ] If `result["success"]` is False: map reason to error message and send (AC: #3, #4, #5)
  - [ ] If `result["success"]` is True: broadcast `entity_moved` to room (AC: #1, #2)
  - [ ] Do NOT handle exit transitions — that's Story 2.3
- [ ] Task 2: Register `handle_move` in `Game._register_handlers()` (AC: #1)
  - [ ] Import `handle_move` from `server.net.handlers.movement`
  - [ ] Register: `self.router.register("move", lambda ws, d: handle_move(ws, d, game=self))`
- [ ] Task 3: Write tests `tests/test_movement.py` (AC: #1-7)
  - [ ] Test successful move updates position and returns entity_moved broadcast
  - [ ] Test move into wall returns "Tile not walkable"
  - [ ] Test move out of bounds returns "Out of bounds"
  - [ ] Test invalid direction returns "Invalid direction: {dir}"
  - [ ] Test move while in combat returns error
  - [ ] Test move without login returns "Not logged in"
  - [ ] Test move broadcasts to other players in room
  - [ ] Use unit tests with mocked Game object (faster, more isolated than WebSocket integration)
- [ ] Task 4: Verify all tests pass
  - [ ] Run `pytest tests/test_movement.py -v`
  - [ ] Run `pytest tests/ -v` to verify no regressions (79 existing tests)

## Dev Notes

### Architecture Compliance

| Component | File Location |
|-----------|--------------|
| Move handler | `server/net/handlers/movement.py` |
| Handler registration | `server/app.py` → `Game._register_handlers()` |
| Movement logic | `server/room/room.py` → `RoomInstance.move_entity()` (existing) |
| Connection tracking | `server/net/connection_manager.py` (existing) |

### Handler Pattern

All handlers follow the signature established in Story 1.8:

```python
async def handle_move(websocket: WebSocket, data: dict, *, game: Game) -> None:
```

The `game` kwarg is passed via lambda closure in `_register_handlers()`.

### Movement Logic (Already Implemented)

`RoomInstance.move_entity(entity_id, direction)` in `server/room/room.py` already handles:
- Direction validation (up/down/left/right)
- Bounds checking
- Walkability checking (via `tile.is_walkable()`)
- Position update on success
- Exit detection (returns `exit` key in result)
- Mob encounter detection (returns `mob_encounter` key)

Return format:
```python
# Success: {"success": True, "x": 6, "y": 5}
# Success with exit: {"success": True, "x": 9, "y": 5, "exit": {...}}
# Failure: {"success": False, "reason": "wall"|"bounds"|"invalid_direction"|"entity_not_found"}
```

### Error Mapping

Map `move_entity` failure reasons to user-facing messages:
```python
ERROR_MESSAGES = {
    "wall": "Tile not walkable",
    "bounds": "Out of bounds",
    "invalid_direction": None,  # Special case: include the direction
    "entity_not_found": "Not logged in",
}
```

For `invalid_direction`, format as: `f"Invalid direction: {direction}"`

### Broadcast Pattern

On successful move, broadcast to all players in the room (including the mover):
```python
await game.connection_manager.broadcast_to_room(
    room_key,
    {"type": "entity_moved", "entity_id": entity_id, "x": result["x"], "y": result["y"]}
)
```

Note: broadcast includes the mover — the client needs the confirmation. No `exclude=` parameter here.

### Login Check Pattern

```python
entity_id = game.connection_manager.get_entity_id(websocket)
if entity_id is None:
    await websocket.send_json({"type": "error", "detail": "Not logged in"})
    return

player_info = game.player_entities.get(entity_id)
if player_info is None:
    await websocket.send_json({"type": "error", "detail": "Not logged in"})
    return

entity = player_info["entity"]
room_key = player_info["room_key"]
```

### Testing Strategy

Use **unit tests with mocked Game** — faster and more isolated than WebSocket integration tests:

```python
@pytest.mark.asyncio
async def test_move_success():
    game = Game()
    room = RoomInstance("test", "Test", 5, 5, [[0]*5 for _ in range(5)])
    entity = PlayerEntity(id="player_1", name="hero", x=2, y=2, player_db_id=1)
    room.add_entity(entity)
    game.room_manager._rooms["test"] = room

    mock_ws = AsyncMock()
    game.connection_manager.connect("player_1", mock_ws, "test")
    game.player_entities["player_1"] = {"entity": entity, "room_key": "test", "db_id": 1}

    await handle_move(mock_ws, {"action": "move", "direction": "right"}, game=game)

    # Verify broadcast was sent
    mock_ws.send_json.assert_called_with(
        {"type": "entity_moved", "entity_id": "player_1", "x": 3, "y": 2}
    )
```

### Anti-Patterns to Avoid

- **DO NOT** handle exit tile transitions — Story 2.3 handles that
- **DO NOT** handle mob encounters — that comes in Epic 4
- **DO NOT** save position to DB on every move — only saved on disconnect (already in Game.handle_disconnect)
- **DO NOT** create protocol.py message schemas — use plain dicts
- **DO NOT** add rate limiting or move throttling — not in scope
- **DO NOT** modify `RoomInstance.move_entity()` — it already works correctly

### Previous Story Intelligence

From Story 1.8:
- Handler signature: `async def handler(websocket, data, *, game)`
- Game owns: `router`, `connection_manager`, `room_manager`, `player_entities`
- `player_entities` dict: `entity_id → {"entity": PlayerEntity, "room_key": str, "db_id": int}`
- ConnectionManager has `get_entity_id(websocket)` for reverse WebSocket lookup
- Handlers registered in `Game._register_handlers()` with lambda wrappers
- 79 existing tests must not regress

### Project Structure Notes

- New files: `server/net/handlers/movement.py`, `tests/test_movement.py`
- Modified files: `server/app.py` (add move handler registration in `_register_handlers`)
- `server/net/handlers/__init__.py` already exists (empty)

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#8.2 Client Actions — move]
- [Source: _bmad-output/planning-artifacts/architecture.md#8.3 Server Messages — entity_moved]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.1]
- [Source: _bmad-output/implementation-artifacts/1-8-game-orchestrator-and-server-lifecycle.md#Dev Agent Record]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References
None

### Completion Notes List
- `server/net/handlers/movement.py`: handle_move validates login, combat state, delegates to room.move_entity(), maps failure reasons to user-facing errors, broadcasts entity_moved on success
- Registered "move" action in Game._register_handlers() with lambda wrapper
- Error mapping: wall→"Tile not walkable", bounds→"Out of bounds", invalid_direction→"Invalid direction: {dir}"
- Broadcast includes mover (no exclude) — client needs position confirmation
- 11 new tests (90 total), all passing — covers all 4 directions, wall/bounds/invalid_direction errors, combat lock, not-logged-in, broadcast to other players, missing direction

### File List
- `server/net/handlers/movement.py` (new) — Movement WebSocket handler
- `server/app.py` (modified) — Added move handler registration
- `tests/test_movement.py` (new) — 11 movement and collision tests
