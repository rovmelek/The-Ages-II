# Story 1.7: Player Login & Room Entry

Status: done

## Story

As a returning player,
I want to login and be placed in my last room seeing the full map,
So that I can continue playing where I left off.

## Acceptance Criteria

1. Client sends `{"action": "login", "username": "hero", "password": "secret123"}` and the password is verified against the bcrypt hash
2. A `PlayerEntity` is created with the player's saved position and stats
3. The entity is placed in the player's `current_room_id` via RoomInstance
4. Client receives `{"type": "login_success", "player_id": 1, "username": "hero"}`
5. Client receives a `room_state` message with full tile grid, all entities, and objects
6. Other players in the room receive an `entity_entered` message with the new player's info
7. Invalid credentials (wrong username or wrong password) returns error: `"Invalid username or password"`
8. Empty username or password returns error: `"Username and password required"`

## Tasks / Subtasks

- [x] Task 1: Add `handle_login` to `server/net/handlers/auth.py` (AC: #1, #2, #3, #4, #5, #6, #7, #8)
  - [x] Extract and validate username/password — empty checks first (AC: #8)
  - [x] Look up player by username via `player_repo.get_by_username(session, username)`
  - [x] Verify password with `auth.verify_password(password, player.password_hash)` (AC: #1)
  - [x] Return `"Invalid username or password"` for missing user OR wrong password (same error, no user enumeration) (AC: #7)
  - [x] Create `PlayerEntity` with id=`f"player_{player.id}"`, name, position, stats from DB (AC: #2)
  - [x] Load room: get from `room_manager.get_room()` or load from DB via `room_repo.get_by_key()` + `room_manager.load_room()` (AC: #3)
  - [x] Add entity to room via `room.add_entity(entity)` (AC: #3)
  - [x] Register connection via `connection_manager.connect(entity_id, websocket, room_key)` (AC: #3)
  - [x] Send `login_success` message (AC: #4)
  - [x] Send `room_state` message via `room.get_state()` (AC: #5)
  - [x] Broadcast `entity_entered` to other players via `connection_manager.broadcast_to_room()` (AC: #6)
- [x] Task 2: Handle the "no room" / first-login scenario
  - [x] If `player.current_room_id` is None (new registration, never logged in), use a default starting room key (e.g., `"test_room"`)
  - [x] If room cannot be found/loaded, send error: `"Room not found"`
- [x] Task 3: Register `handle_login` in `server/net/websocket.py` (AC: #1)
  - [x] Import `handle_login` from `server.net.handlers.auth`
  - [x] Register with `router.register("login", handle_login)`
- [x] Task 4: Pass shared dependencies to the login handler
  - [x] The handler needs access to `connection_manager`, `room_manager`, and DB session
  - [x] Since Game orchestrator (Story 1.8) doesn't exist yet, use module-level imports from `websocket.py` for `connection_manager` and create a module-level `room_manager` in `websocket.py`
  - [x] Alternative: pass dependencies via closure/partial when registering the handler
  - [x] Choose the simplest approach that's easy to refactor in Story 1.8
- [x] Task 5: Write tests `tests/test_login.py` (AC: #1-8)
  - [x] Test successful login returns login_success with player_id and username
  - [x] Test successful login returns room_state with tiles, entities, exits
  - [x] Test login creates PlayerEntity at saved position
  - [x] Test login broadcasts entity_entered to other players in room
  - [x] Test invalid username returns error
  - [x] Test wrong password returns error (same message as invalid username)
  - [x] Test empty username returns error
  - [x] Test empty password returns error
  - [x] Test login with no current_room_id uses default starting room
  - [x] Use in-memory SQLite + patched dependencies for test isolation
- [x] Task 6: Verify all tests pass
  - [x] Run `pytest tests/test_login.py -v`
  - [x] Run `pytest tests/ -v` to verify no regressions (57 existing tests)

## Dev Notes

### Architecture Compliance

| Component | File Location |
|-----------|--------------|
| Login handler | `server/net/handlers/auth.py` (add to existing file) |
| Handler registration | `server/net/websocket.py` (add login registration) |
| PlayerEntity | `server/player/entity.py` (existing — use as-is) |
| RoomInstance | `server/room/room.py` (existing — use add_entity, get_state) |
| RoomManager | `server/room/manager.py` (existing — use get_room, load_room) |
| ConnectionManager | `server/net/connection_manager.py` (existing — use connect, broadcast_to_room) |
| Password verification | `server/player/auth.py` (existing — use verify_password) |

### Handler Dependency Pattern

The login handler needs access to `connection_manager`, `room_manager`, and DB. Since the Game orchestrator doesn't exist yet (Story 1.8), the simplest approach is to import the module-level instances from `websocket.py` and create a `room_manager` there too:

```python
# In server/net/websocket.py — add:
from server.room.manager import RoomManager
room_manager = RoomManager()

# In server/net/handlers/auth.py — the handler accesses them:
from server.net import websocket as ws_module
# Use ws_module.connection_manager, ws_module.room_manager
```

Or use a closure/functools.partial when registering. Choose whichever is cleanest. Story 1.8 will refactor all of this into the Game class.

### Login Flow (Step by Step)

```python
async def handle_login(websocket: WebSocket, data: dict) -> None:
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        await websocket.send_json({"type": "error", "detail": "Username and password required"})
        return

    async with async_session() as session:
        player = await player_repo.get_by_username(session, username)
        if player is None or not verify_password(password, player.password_hash):
            await websocket.send_json({"type": "error", "detail": "Invalid username or password"})
            return

        # Create runtime entity
        entity_id = f"player_{player.id}"
        entity = PlayerEntity(
            id=entity_id,
            name=player.username,
            x=player.position_x,
            y=player.position_y,
            player_db_id=player.id,
            stats=player.stats or {},
        )

        # Determine room
        room_key = player.current_room_id or "test_room"

        # Load room if needed
        room = room_manager.get_room(room_key)
        if room is None:
            room_db = await room_repo.get_by_key(session, room_key)
            if room_db is None:
                await websocket.send_json({"type": "error", "detail": "Room not found"})
                return
            room = room_manager.load_room(room_db)

        # Place entity and register connection
        room.add_entity(entity)
        connection_manager.connect(entity_id, websocket, room_key)

        # Send responses
        await websocket.send_json({"type": "login_success", "player_id": player.id, "username": player.username})
        await websocket.send_json({"type": "room_state", **room.get_state()})

        # Notify others
        entity_data = {"id": entity.id, "name": entity.name, "x": entity.x, "y": entity.y}
        await connection_manager.broadcast_to_room(room_key, {"type": "entity_entered", "entity": entity_data}, exclude=entity_id)
```

### Key Existing Signatures

**PlayerEntity** dataclass (`server/player/entity.py`):
```python
@dataclass
class PlayerEntity:
    id: str           # e.g., "player_1"
    name: str
    x: int
    y: int
    player_db_id: int
    stats: dict = field(default_factory=dict)
    in_combat: bool = False
```

**ConnectionManager** (`server/net/connection_manager.py`):
```python
def connect(self, entity_id: str, websocket: WebSocket, room_key: str) -> None
def disconnect(self, entity_id: str) -> None
async def broadcast_to_room(self, room_key: str, message: dict, exclude: str | None = None) -> None
```

**RoomManager** (`server/room/manager.py`):
```python
def get_room(self, room_key: str) -> RoomInstance | None
def load_room(self, room_db: RoomModel) -> RoomInstance   # takes a DB model, not a key!
```

**RoomInstance** (`server/room/room.py`):
```python
def add_entity(self, entity: PlayerEntity) -> None
def remove_entity(self, entity_id: str) -> PlayerEntity | None
def get_player_ids(self) -> list[str]
def get_state(self) -> dict   # returns {room_key, name, width, height, tiles, entities, exits}
```

**RoomRepo** (`server/room/repo.py`):
```python
async def get_by_key(session: AsyncSession, room_key: str) -> Room | None
```

**PlayerRepo** (`server/player/repo.py`):
```python
async def get_by_username(session: AsyncSession, username: str) -> Player | None
```

### Room State Message Format

`room.get_state()` returns:
```python
{
    "room_key": "test_room",
    "name": "Test Room",
    "width": 5,
    "height": 5,
    "tiles": [[0, 0, ...], ...],   # 2D grid of TileType int values
    "entities": [{"id": "player_1", "name": "hero", "x": 2, "y": 2}, ...],
    "exits": [{"x": 4, "y": 4, "target_room": "cave_1", "entry_x": 0, "entry_y": 0}]
}
```

The `room_state` message wraps this: `{"type": "room_state", **room.get_state()}`

### Entity Entered Message Format

```python
{"type": "entity_entered", "entity": {"id": "player_1", "name": "hero", "x": 2, "y": 2}}
```

### Testing Strategy

Login tests need more setup than registration:
- Create a player in the DB (register first, or insert directly)
- Set up a room in the DB (or pre-load RoomInstance into room_manager)
- Patch `async_session`, `connection_manager`, and `room_manager` in the handler

For WebSocket integration tests with TestClient:
- Register a player first, then login in a new connection
- Pre-load a room into the room_manager before login
- Verify both messages (login_success + room_state) arrive in order

For entity_entered broadcast testing:
- Connect two WebSocket clients
- Register+login player A, then register+login player B
- Player A should receive entity_entered for player B

### Existing Test Room

`data/rooms/test_room.json` — 5x5 room with floor tiles, exit at [4,4], player spawn at (2,2). Use this for testing.

### Anti-Patterns to Avoid

- **DO NOT** create the Game class or lifecycle management — that's Story 1.8
- **DO NOT** implement disconnect/cleanup logic — that comes with Game orchestrator
- **DO NOT** implement room transitions (move + exit) — that's Story 2.3
- **DO NOT** create `protocol.py` message schemas — use plain dicts
- **DO NOT** persist position changes on login — login just restores saved state
- **DO NOT** handle "already logged in" deduplication — keep it simple for now

### Previous Story Intelligence

From Story 1.6:
- `server/net/handlers/auth.py` exists with `handle_register` — add `handle_login` to same file
- Handler uses `async_session()` from `server.core.database` for DB access
- `server/net/websocket.py` has module-level `router` and `connection_manager`
- Tests use `unittest.mock.patch` to replace `async_session` in handler module
- TestClient (sync) for WebSocket integration tests
- 57 existing tests must not regress
- `server/player/auth.py` has `verify_password(password, password_hash)` ready to use

### Project Structure Notes

- Modified files: `server/net/handlers/auth.py`, `server/net/websocket.py`
- New files: `tests/test_login.py`
- May need to add `room_manager` instance to `server/net/websocket.py` (temporary until Story 1.8)

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#8. Networking Protocol]
- [Source: _bmad-output/planning-artifacts/architecture.md#9.1 Player table]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.7]
- [Source: THE_AGES_SERVER_PLAN.md#server/net/handlers/auth.py — handle_login]
- [Source: _bmad-output/implementation-artifacts/1-6-player-registration.md#Dev Agent Record]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References
None

### Completion Notes List
- `handle_login` added to `server/net/handlers/auth.py` — validates credentials, creates PlayerEntity, loads/gets room, places entity, sends login_success + room_state, broadcasts entity_entered
- Dependency pattern: handler uses lazy import `from server.net import websocket as ws_module` to access `connection_manager` and `room_manager` — avoids circular imports, easy to refactor in Story 1.8
- Added `room_manager = RoomManager()` to `server/net/websocket.py` as temporary module-level instance
- Default room fallback: `player.current_room_id or "test_room"` for first-login scenario
- Room loading: checks room_manager cache first, falls back to DB load via room_repo.get_by_key + room_manager.load_room
- 11 new tests (68 total), all passing — covers success flow, room_state contents, entity_entered broadcast, all error cases, default room, room-not-found
- Tests patch async_session, room_manager, and connection_manager for isolation

### File List
- `server/net/handlers/auth.py` (modified) — Added handle_login, imports for verify_password, PlayerEntity, room_repo
- `server/net/websocket.py` (modified) — Added RoomManager import, room_manager instance, login handler registration
- `tests/test_login.py` (new) — 11 login and room entry tests
