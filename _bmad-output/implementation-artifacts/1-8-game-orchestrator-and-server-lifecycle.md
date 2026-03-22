# Story 1.8: Game Orchestrator & Server Lifecycle

Status: done

## Story

As a developer,
I want the Game class to tie all managers together with proper startup/shutdown,
So that the server initializes everything correctly and handles player disconnects.

## Acceptance Criteria

1. `Game.startup()` initializes the database (tables created)
2. `Game.startup()` loads rooms from JSON via JsonRoomProvider into DB and then into memory
3. `Game.startup()` loads card definitions from JSON into DB (if card files exist)
4. `Game.startup()` registers all message handlers with the MessageRouter
5. GET `/health` returns `{"status": "ok"}`
6. On WebSocket disconnect: player's position is saved to DB, entity removed from room, `entity_left` broadcast to room, player removed from tracking
7. `Game.shutdown()` cancels all active timers and cleans up

## Tasks / Subtasks

- [x] Task 1: Create `Game` class in `server/app.py` (AC: #1, #2, #3, #4)
  - [x] Game owns: `router`, `connection_manager`, `room_manager`, `player_entities` dict
  - [x] `async startup()`: call `init_db()`, load rooms via `JsonRoomProvider.load_rooms()`, load each room into `room_manager`, load cards if files exist, register handlers
  - [x] `shutdown()`: cleanup (timer cancellation — create minimal stub for now)
  - [x] `_register_handlers()`: register login + register with lambda wrappers passing `game=self`
- [x] Task 2: Refactor handlers to accept `game` kwarg (AC: #4)
  - [x] Change `handle_register(websocket, data)` → `handle_register(websocket, data, *, game)` (game not needed for register, but consistent signature)
  - [x] Change `handle_login(websocket, data)` → `handle_login(websocket, data, *, game)` — use `game.connection_manager`, `game.room_manager` instead of lazy import from ws_module
  - [x] Remove module-level instances from `server/net/websocket.py` (router, connection_manager, room_manager, handler registrations)
- [x] Task 3: Refactor `server/app.py` with FastAPI lifespan and WebSocket endpoint (AC: #5)
  - [x] Use `@asynccontextmanager` lifespan for startup/shutdown
  - [x] Move WebSocket endpoint into `app.py` using `game.router`
  - [x] Add `GET /health` returning `{"status": "ok"}`
  - [x] Handle `WebSocketDisconnect` by calling `game.handle_disconnect(websocket)`
- [x] Task 4: Implement `handle_disconnect` on Game (AC: #6)
  - [x] Find entity_id from websocket (need reverse lookup — add `get_entity_id(websocket)` to ConnectionManager)
  - [x] Save player position to DB via `player_repo.update_position()`
  - [x] Remove entity from room via `room.remove_entity(entity_id)`
  - [x] Broadcast `entity_left` to other players in room
  - [x] Remove from `connection_manager` and `player_entities`
- [x] Task 5: Add `get_entity_id(websocket)` to ConnectionManager (AC: #6)
  - [x] Add reverse lookup: `_ws_to_entity: dict[int, str]` mapping `id(websocket)` → entity_id
  - [x] Update `connect()` to populate reverse map
  - [x] Update `disconnect()` to clean reverse map (accept websocket OR entity_id)
- [x] Task 6: Update `server/net/websocket.py` to be minimal (AC: #4)
  - [x] Remove module-level router, connection_manager, room_manager
  - [x] Remove handler registrations
  - [x] Keep only the `websocket_endpoint` function if needed, or remove entirely if endpoint moves to app.py
- [x] Task 7: Write tests (AC: #1-7)
  - [x] Test health endpoint returns `{"status": "ok"}`
  - [x] Test Game.startup() initializes database
  - [x] Test Game.startup() loads rooms into room_manager
  - [x] Test Game.startup() registers handlers
  - [x] Test disconnect saves position, removes entity, broadcasts entity_left
  - [x] Test Game.shutdown() completes without error
  - [x] Verify no regressions (68 existing tests — some may need updates due to refactoring)
- [x] Task 8: Fix existing tests broken by refactoring
  - [x] Update test_auth.py patches (async_session location, handler signature changes)
  - [x] Update test_login.py patches (no more ws_module imports in handler)
  - [x] Update test_websocket.py if websocket module changes
  - [x] Run full suite: `pytest tests/ -v`

## Dev Notes

### Architecture Compliance

| Component | File Location |
|-----------|--------------|
| Game class | `server/app.py` |
| FastAPI app + lifespan | `server/app.py` |
| Health endpoint | `server/app.py` |
| WebSocket endpoint | `server/app.py` (moved from websocket.py) |
| ConnectionManager (updated) | `server/net/connection_manager.py` |
| websocket.py | `server/net/websocket.py` (gutted or removed) |

### Game Class Design

```python
class Game:
    def __init__(self):
        self.router = MessageRouter()
        self.connection_manager = ConnectionManager()
        self.room_manager = RoomManager()
        self.player_entities: dict[str, dict] = {}  # entity_id → {"entity", "room_key", "db_id"}

    async def startup(self):
        await init_db()
        # Load rooms
        async with async_session() as session:
            provider = JsonRoomProvider()
            rooms = await provider.load_rooms(session)
            for room_db in rooms:
                self.room_manager.load_room(room_db)
        # Load cards (skip if no files)
        # Register handlers
        self._register_handlers()

    def shutdown(self):
        pass  # Timer cancellation when TimerService exists

    def _register_handlers(self):
        from server.net.handlers.auth import handle_login, handle_register
        self.router.register("login", lambda ws, d: handle_login(ws, d, game=self))
        self.router.register("register", lambda ws, d: handle_register(ws, d, game=self))
```

### Handler Signature Change

```python
# Before (Story 1.6/1.7):
async def handle_register(websocket: WebSocket, data: dict) -> None:
    ...

# After (Story 1.8):
async def handle_register(websocket: WebSocket, data: dict, *, game) -> None:
    # Use game.connection_manager, game.room_manager if needed
    ...
```

The `game` kwarg is keyword-only. For `handle_register`, the game reference isn't used (registration only needs DB), but the signature is kept consistent. For `handle_login`, replace `ws_module.*` references with `game.*`.

### Disconnect Flow

```python
async def handle_disconnect(self, websocket: WebSocket):
    entity_id = self.connection_manager.get_entity_id(websocket)
    if entity_id is None:
        return  # Unauthenticated connection, nothing to clean up

    player_info = self.player_entities.pop(entity_id, None)
    if player_info:
        entity = player_info["entity"]
        room_key = player_info["room_key"]

        # Save position
        async with async_session() as session:
            await player_repo.update_position(session, entity.player_db_id, room_key, entity.x, entity.y)

        # Remove from room and notify
        room = self.room_manager.get_room(room_key)
        if room:
            room.remove_entity(entity_id)
            await self.connection_manager.broadcast_to_room(
                room_key, {"type": "entity_left", "entity_id": entity_id}, exclude=entity_id
            )

    self.connection_manager.disconnect(entity_id)
```

### ConnectionManager Changes

Add reverse WebSocket → entity_id lookup:

```python
def __init__(self):
    self._connections: dict[str, WebSocket] = {}
    self._player_rooms: dict[str, str] = {}
    self._ws_to_entity: dict[int, str] = {}  # id(websocket) → entity_id

def connect(self, entity_id, websocket, room_key):
    self._connections[entity_id] = websocket
    self._player_rooms[entity_id] = room_key
    self._ws_to_entity[id(websocket)] = entity_id

def get_entity_id(self, websocket: WebSocket) -> str | None:
    return self._ws_to_entity.get(id(websocket))

def disconnect(self, entity_id):
    ws = self._connections.pop(entity_id, None)
    self._player_rooms.pop(entity_id, None)
    if ws:
        self._ws_to_entity.pop(id(ws), None)
```

### FastAPI Lifespan Pattern

```python
from contextlib import asynccontextmanager

game = Game()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await game.startup()
    yield
    game.shutdown()

app = FastAPI(title="The Ages II", lifespan=lifespan)
```

### Login Handler Refactor

In `handle_login`, replace:
```python
from server.net import websocket as ws_module
ws_module.room_manager.get_room(...)
ws_module.connection_manager.connect(...)
```
With:
```python
game.room_manager.get_room(...)
game.connection_manager.connect(...)
```

And track in player_entities:
```python
game.player_entities[entity_id] = {"entity": entity, "room_key": room_key, "db_id": player.id}
```

### Existing Code to Reuse

- `server/core/database.py`: `init_db()`, `async_session`
- `server/room/provider.py`: `JsonRoomProvider.load_rooms(session)` — returns list of Room DB models
- `server/room/manager.py`: `RoomManager.load_room(room_db)` — takes Room DB model
- `server/combat/cards/card_repo.py`: `load_cards_from_json(session, path)` — takes path to JSON
- `server/player/repo.py`: `update_position(session, player_id, room_key, x, y)`
- `server/net/connection_manager.py`: existing connect/disconnect/broadcast
- `server/net/message_router.py`: existing register/route

### Testing Strategy

- **Health endpoint**: simple GET test via TestClient
- **Startup**: create Game, call startup with in-memory DB, verify room_manager has rooms
- **Disconnect**: register+login a player, then simulate disconnect, verify position saved and entity removed
- **Existing tests**: will need patch updates since handler signatures change and module-level instances are removed

### Anti-Patterns to Avoid

- **DO NOT** create CombatManager, TimerService, or MobEntity — those come in later epics
- **DO NOT** implement mob spawning — no mobs in Epic 1
- **DO NOT** add movement, chat, combat, or inventory handlers — only auth handlers exist
- **DO NOT** create protocol.py — keep using plain dicts

### Previous Story Intelligence

From Story 1.7:
- Handlers currently use lazy import from `server.net.websocket` module for shared instances
- Tests patch `async_session`, `connection_manager`, `room_manager` separately
- TestClient (sync) for WebSocket integration tests
- 68 existing tests — expect breakage from refactoring, budget time to fix

### Project Structure Notes

- Modified: `server/app.py`, `server/net/handlers/auth.py`, `server/net/connection_manager.py`, `server/net/websocket.py`
- New: `tests/test_game.py`
- Modified: `tests/test_auth.py`, `tests/test_login.py`, `tests/test_websocket.py` (patch updates)

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#3.2 System Ownership]
- [Source: _bmad-output/planning-artifacts/architecture.md#8. Networking Protocol]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.8]
- [Source: THE_AGES_SERVER_PLAN.md#Game class]
- [Source: _bmad-output/implementation-artifacts/1-7-player-login-and-room-entry.md#Dev Agent Record]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References
None

### Completion Notes List
- Game class in `server/app.py` — owns router, connection_manager, room_manager, player_entities
- `startup()`: calls init_db, loads rooms via JsonRoomProvider → room_manager, loads cards if files exist, registers handlers via lambda wrappers
- `shutdown()`: stub for timer cancellation (TimerService comes in later epics)
- `handle_disconnect()`: reverse WebSocket lookup → save position (best-effort) → remove entity from room → broadcast entity_left → clean up connection
- ConnectionManager: added `_ws_to_entity` reverse map, `get_entity_id(websocket)`, `get_room(entity_id)`
- Handler signatures changed to `(websocket, data, *, game)` — game passed via lambda closure in `_register_handlers()`
- `server/net/websocket.py` gutted — now only has `create_websocket_endpoint()` factory (unused, endpoint is in app.py)
- FastAPI lifespan pattern for startup/shutdown
- `/health` endpoint returns `{"status": "ok"}`
- WebSocket endpoint in app.py calls `game.handle_disconnect(websocket)` on `WebSocketDisconnect`
- Login handler now tracks player in `game.player_entities[entity_id]`
- 9 new tests (79 total), all passing — 4 disconnect unit tests, 3 startup tests, 1 health, 1 shutdown
- Fixed all 68 existing tests: updated patches for new handler signatures and game object references
- 15 websocket tests updated to use `game.router` instead of `ws_module.router`

### File List
- `server/app.py` (rewritten) — Game class, FastAPI app with lifespan, health endpoint, WebSocket endpoint
- `server/net/handlers/auth.py` (modified) — Handler signatures changed to accept `game` kwarg, login uses `game.*` instead of ws_module
- `server/net/connection_manager.py` (modified) — Added `_ws_to_entity` reverse map, `get_entity_id()`, `get_room()`
- `server/net/websocket.py` (rewritten) — Gutted module-level instances, now just has factory function
- `tests/test_game.py` (new) — 9 tests for Game lifecycle, startup, disconnect, health
- `tests/test_websocket.py` (modified) — Updated to use `game.router` instead of `ws_module.router`
- `tests/test_login.py` (modified) — Updated patches for game object dependencies
- `tests/test_auth.py` (unchanged) — Still passes with lambda wrapper
