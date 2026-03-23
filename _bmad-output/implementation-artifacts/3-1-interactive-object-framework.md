# Story 3.1: Interactive Object Framework

Status: done

## Story

As a player,
I want to interact with objects in the room that respond to my actions,
So that the world feels dynamic and explorable.

## Acceptance Criteria

1. Client sends `{"action": "interact", "target_id": "chest_01"}` and the server identifies the object in the current room and delegates to the appropriate interaction handler based on object type
2. Client receives `{"type": "interact_result", ...}` with the outcome of the interaction
3. Player tries to interact with an object that doesn't exist → error: `"Object not found"`
4. Interactive object with `state_scope: "player"` loads state from `PlayerObjectState` for that specific player
5. Interactive object with `state_scope: "room"` loads state from `RoomState.dynamic_state`, shared across all players
6. Player not logged in receives error: `"Not logged in"`

## Tasks / Subtasks

- [ ] Task 1: Create `server/room/objects/base.py` with `RoomObject` base class (AC: #1, #2)
  - [ ] Define `RoomObject` dataclass with `id`, `type`, `x`, `y`, `category`, `state_scope`, `config`
  - [ ] Define `InteractiveObject` subclass with `async def interact(player_id, game) -> dict` abstract method
- [ ] Task 2: Create `server/room/objects/registry.py` with object type registry (AC: #1)
  - [ ] Define `OBJECT_HANDLERS: dict[str, Type[InteractiveObject]]` mapping object type strings to classes
  - [ ] Define `create_object(obj_dict) -> RoomObject` factory function that builds the right object from JSON
- [ ] Task 3: Create `server/room/objects/state.py` with state loading helpers (AC: #4, #5)
  - [ ] `async def get_player_object_state(session, player_id, room_key, object_id) -> dict` — reads from PlayerObjectState table
  - [ ] `async def set_player_object_state(session, player_id, room_key, object_id, state_data) -> None` — upserts PlayerObjectState
  - [ ] `async def get_room_object_state(session, room_key, object_id) -> dict` — reads from RoomState.dynamic_state
  - [ ] `async def set_room_object_state(session, room_key, object_id, state_data) -> None` — upserts into RoomState.dynamic_state
- [ ] Task 4: Create `server/net/handlers/interact.py` with `handle_interact` (AC: #1-6)
  - [ ] Define `async def handle_interact(websocket, data, *, game) -> None`
  - [ ] Login check: `game.connection_manager.get_entity_id(websocket)` → error if None (AC: #6)
  - [ ] Extract `target_id` from data
  - [ ] Find object in current room's objects list by id matching `target_id` (AC: #3)
  - [ ] Look up handler in object registry by object type
  - [ ] Call handler's `interact()` method and return `interact_result` (AC: #2)
- [ ] Task 5: Register `handle_interact` in `Game._register_handlers()` (AC: #1)
  - [ ] Import and register: `self.router.register("interact", lambda ws, d: handle_interact(ws, d, game=self))`
- [ ] Task 6: Update `RoomInstance` to parse interactive objects (AC: #1)
  - [ ] In `__init__`, build a dict `self._interactive_objects: dict[str, dict]` mapping object id → object dict for quick lookup
  - [ ] Add `get_object(object_id) -> dict | None` method
- [ ] Task 7: Write tests `tests/test_interact.py` (AC: #1-6)
  - [ ] Test interact with valid object returns interact_result
  - [ ] Test interact with nonexistent object returns "Object not found"
  - [ ] Test not logged in returns error
  - [ ] Test player-scoped state loading
  - [ ] Test room-scoped state loading
  - [ ] Test state persistence (write then read)
- [ ] Task 8: Verify all tests pass
  - [ ] Run `pytest tests/test_interact.py -v`
  - [ ] Run `pytest tests/ -v` to verify no regressions (117 existing tests)

## Dev Notes

### Architecture Compliance

| Component | File Location |
|-----------|--------------|
| RoomObject base | `server/room/objects/base.py` |
| Object registry | `server/room/objects/registry.py` |
| State helpers | `server/room/objects/state.py` |
| Interact handler | `server/net/handlers/interact.py` |
| Handler registration | `server/app.py` → `Game._register_handlers()` |
| Room instance updates | `server/room/room.py` |

### Object JSON Format (from architecture.md §4)

Interactive objects in room JSON `objects` array:
```json
{
  "id": "chest_01",
  "type": "chest",
  "category": "interactive",
  "x": 15, "y": 22,
  "state_scope": "player",
  "config": {
    "loot_table": "common_chest",
    "locked": false
  }
}
```

### State Scope Design (from architecture.md §4.2)

- `"player"` scope: Uses `PlayerObjectState` table (already exists in `server/room/models.py:32-42`)
  - Unique constraint on `(player_id, room_key, object_id)`
- `"room"` scope: Uses `RoomState.dynamic_state` JSON column (already exists in `server/room/models.py:23-29`)

### Interact Message Protocol (from architecture.md §8)

Client → Server:
```json
{"action": "interact", "target_id": "chest_01"}
```

Server → Client:
```json
{"type": "interact_result", "object_id": "chest_01", "result": { ... }}
```

Error:
```json
{"type": "error", "detail": "Object not found"}
```

### Existing Infrastructure to Reuse

- **DB models already exist**: `PlayerObjectState` and `RoomState` in `server/room/models.py` — DO NOT recreate
- **Room repo already exists**: `server/room/repo.py` has `get_state()`, `save_state()` for RoomState — reuse for room-scoped state
- **Room objects directory**: `server/room/objects/` exists with `__init__.py` — add files here
- **Handler pattern**: Follow `server/net/handlers/chat.py` pattern — `async def handle_interact(websocket, data, *, game)`
- **Login check**: `game.connection_manager.get_entity_id(websocket)` → `game.player_entities[entity_id]`
- **Player DB ID**: Available via `game.player_entities[entity_id]["db_id"]` for PlayerObjectState lookups

### Anti-Patterns to Avoid

- **DO NOT** implement chest or lever logic in this story — Story 3.2 and 3.3 add specific object types
- **DO NOT** create new DB models — PlayerObjectState and RoomState already exist
- **DO NOT** add NPC interaction — that's Story 3.4
- **DO** create a minimal "echo" or "generic" interactive object type for testing the framework
- **DO** keep the interact handler thin — it delegates to object-specific handlers

### Previous Story Intelligence

From Epic 2 stories:
- Handler signature: `async def handler(websocket, data, *, game)`
- Login check pattern: `game.connection_manager.get_entity_id(websocket)` → look up `game.player_entities`
- Handler registration in `Game._register_handlers()` with lambda closure
- `RoomInstance` stores objects as `self.objects: list[dict]`
- Static objects processed in `__init__` (category == "static", blocking flag)
- 117 existing tests must not regress

### Project Structure Notes

- New files: `server/room/objects/base.py`, `server/room/objects/registry.py`, `server/room/objects/state.py`, `server/net/handlers/interact.py`, `tests/test_interact.py`
- Modified files: `server/app.py` (handler registration), `server/room/room.py` (interactive object lookup)

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#4 Room Object System]
- [Source: _bmad-output/planning-artifacts/architecture.md#4.2 State Scope]
- [Source: _bmad-output/planning-artifacts/architecture.md#8.2 Client Actions — interact]
- [Source: _bmad-output/planning-artifacts/architecture.md#8.3 Server Messages — interact_result]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.1]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References
None

### Completion Notes List
- `server/room/objects/base.py`: RoomObject dataclass + InteractiveObject base with abstract `interact()` method
- `server/room/objects/registry.py`: OBJECT_HANDLERS dict, `register_object_type()`, `create_object()` factory
- `server/room/objects/state.py`: Player-scoped and room-scoped state CRUD helpers using existing PlayerObjectState and RoomState models
- `server/net/handlers/interact.py`: handle_interact validates login, finds object in room, delegates to typed handler, returns interact_result
- `server/app.py`: Registered "interact" action in Game._register_handlers()
- `server/room/room.py`: Added `_interactive_objects` index and `get_object()` method
- 12 new tests (129 total), all passing — handler tests, room lookup, state persistence round-trips

### File List
- `server/room/objects/base.py` (new) — RoomObject and InteractiveObject base classes
- `server/room/objects/registry.py` (new) — Object type registry and factory
- `server/room/objects/state.py` (new) — Player-scoped and room-scoped state helpers
- `server/net/handlers/interact.py` (new) — Interact WebSocket handler
- `server/app.py` (modified) — Added interact handler registration
- `server/room/room.py` (modified) — Added interactive object index and get_object()
- `tests/test_interact.py` (new) — 12 interactive object framework tests
