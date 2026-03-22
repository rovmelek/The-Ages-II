# Story 1.6: Player Registration

Status: done

## Story

As a new player,
I want to create an account with a username and password,
So that I can start playing the game.

## Acceptance Criteria

1. Client sends `{"action": "register", "username": "hero", "password": "secret123"}` via WebSocket
2. A new player is created in the database with bcrypt-hashed password
3. Client receives `{"type": "login_success", "player_id": 1, "username": "hero"}`
4. Username shorter than 3 characters returns error: `"Username must be at least 3 characters"`
5. Password shorter than 6 characters returns error: `"Password must be at least 6 characters"`
6. Username that already exists returns error: `"Username already taken"`

## Tasks / Subtasks

- [x] Task 1: Create `server/player/auth.py` (AC: #2)
  - [x] Implement `hash_password(password: str) -> str` — bcrypt hash, returns decoded string
  - [x] Implement `verify_password(password: str, password_hash: str) -> bool` — bcrypt checkpw
  - [x] Both functions are sync (bcrypt is CPU-bound, but fast enough for game use)
- [x] Task 2: Create `server/net/handlers/auth.py` with `handle_register` (AC: #1, #3, #4, #5, #6)
  - [x] Define `async def handle_register(websocket: WebSocket, data: dict) -> None`
  - [x] Validate username: strip whitespace, check `len(username) >= 3`
  - [x] Validate password: check `len(password) >= 6`
  - [x] Check for existing username via `player_repo.get_by_username(session, username)`
  - [x] Hash password via `auth.hash_password(password)`
  - [x] Create player via `player_repo.create(session, username, hashed)`
  - [x] Send success: `{"type": "login_success", "player_id": player.id, "username": player.username}`
  - [x] Send errors as: `{"type": "error", "detail": "..."}`
  - [x] The handler needs a database session — use `database.async_session()` context manager directly
- [x] Task 3: Register the handler in `server/net/websocket.py` (AC: #1)
  - [x] Import `handle_register` from `server.net.handlers.auth`
  - [x] Register with `router.register("register", handle_register)`
  - [x] Keep module-level registration (Game orchestrator will take over in Story 1.8)
- [x] Task 4: Write tests `tests/test_auth.py` (AC: #1-6)
  - [x] Test successful registration creates player with hashed password
  - [x] Test registration returns login_success with player_id and username
  - [x] Test username too short returns error
  - [x] Test password too short returns error
  - [x] Test duplicate username returns error
  - [x] Test hash_password and verify_password round-trip
  - [x] Use in-memory SQLite database for test isolation
- [x] Task 5: Verify all tests pass
  - [x] Run `pytest tests/test_auth.py -v`
  - [x] Run `pytest tests/ -v` to verify no regressions (46 existing tests)

## Dev Notes

### Architecture Compliance

| Component | File Location |
|-----------|--------------|
| Auth logic (bcrypt) | `server/player/auth.py` |
| Register handler | `server/net/handlers/auth.py` |
| Handler registration | `server/net/websocket.py` (temporary, moves to Game in 1.8) |

### Handler Signature

All action handlers follow this signature (established in Story 1.5):

```python
async def handle_register(websocket: WebSocket, data: dict) -> None:
    ...
```

The `game` kwarg from `THE_AGES_SERVER_PLAN.md` is NOT used yet — handlers access the database directly via `database.async_session()`. The Game orchestrator (Story 1.8) will refactor handler wiring later.

### Database Session Pattern

Since Story 1.8's Game orchestrator doesn't exist yet, the handler gets its own session:

```python
from server.core.database import async_session

async def handle_register(websocket: WebSocket, data: dict) -> None:
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if len(username) < 3:
        await websocket.send_json({"type": "error", "detail": "Username must be at least 3 characters"})
        return
    if len(password) < 6:
        await websocket.send_json({"type": "error", "detail": "Password must be at least 6 characters"})
        return

    async with async_session() as session:
        existing = await player_repo.get_by_username(session, username)
        if existing:
            await websocket.send_json({"type": "error", "detail": "Username already taken"})
            return
        hashed = hash_password(password)
        player = await player_repo.create(session, username, hashed)
        await websocket.send_json({"type": "login_success", "player_id": player.id, "username": player.username})
```

### Auth Module Design

```python
# server/player/auth.py
import bcrypt

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())
```

### Testing Strategy

Use an **in-memory SQLite** database to avoid touching the real DB:

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from server.core.database import Base

@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()
```

For WebSocket integration tests, use `TestClient` (sync, established in Story 1.5). You'll need to **patch `async_session`** in the handler module to use the test database, or test the handler directly with mocks.

**Important**: The existing `tests/test_repos.py` already has an `async_engine` and `db_session` fixture — reuse the same pattern but don't import from test_repos (each test file should be independent).

### Existing Code to Reuse

- `server/player/repo.py`: `get_by_username(session, username)`, `create(session, username, password_hash, starting_room_id)`
- `server/player/models.py`: `Player` model with `password_hash` column (String(128))
- `server/net/message_router.py`: `MessageRouter.register(action, handler)`
- `server/net/websocket.py`: module-level `router` instance
- `server/core/database.py`: `async_session`, `Base`, `init_db()`
- `server/net/handlers/__init__.py` already exists (empty)

### Anti-Patterns to Avoid

- **DO NOT** implement login logic — that's Story 1.7
- **DO NOT** create PlayerEntity or place player in a room — registration only creates the DB record
- **DO NOT** use `protocol.py` message schemas — use plain dicts (protocol comes later)
- **DO NOT** create the Game orchestrator or modify `server/app.py` lifecycle — that's Story 1.8
- **DO NOT** import RoomManager or ConnectionManager in the auth handler — not needed for registration
- **DO NOT** add REST API endpoints — WebSocket only for now

### Previous Story Intelligence

From Story 1.5:
- `server/net/websocket.py` has module-level `router = MessageRouter()` and `connection_manager = ConnectionManager()`
- Handler signature: `async def handler(websocket: WebSocket, data: dict) -> None`
- WebSocket endpoint parses JSON, validates `action` field, calls `router.route(websocket, data)`
- TestClient used for sync WebSocket tests, AsyncMock for unit tests
- 46 existing tests must not regress
- `server/net/handlers/__init__.py` exists (empty)

### Project Structure Notes

- New files: `server/player/auth.py`, `server/net/handlers/auth.py`, `tests/test_auth.py`
- `server/player/__init__.py` already exists
- `server/net/handlers/__init__.py` already exists
- bcrypt is already in pyproject.toml dependencies

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#3.1 Directory Structure]
- [Source: _bmad-output/planning-artifacts/architecture.md#8. Networking Protocol]
- [Source: _bmad-output/planning-artifacts/architecture.md#9.3 Players table]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.6]
- [Source: THE_AGES_SERVER_PLAN.md#server/net/handlers/auth.py]
- [Source: _bmad-output/implementation-artifacts/1-5-websocket-connection-and-message-routing.md#Dev Agent Record]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References
None

### Completion Notes List
- `server/player/auth.py`: hash_password (bcrypt.hashpw + gensalt) and verify_password (bcrypt.checkpw), both sync
- `server/net/handlers/auth.py`: handle_register validates username>=3 chars, password>=6 chars, checks duplicate via player_repo, hashes password, creates player, returns login_success
- Handler uses `async_session()` context manager directly (no Game orchestrator yet)
- Registered "register" action in websocket.py module-level router
- 11 new tests (57 total), all passing — 3 unit tests for hash/verify, 8 integration tests via WebSocket TestClient
- Tests patch `async_session` in handler module to use in-memory SQLite

### File List
- `server/player/auth.py` (new) — bcrypt password hashing utilities
- `server/net/handlers/auth.py` (new) — Registration WebSocket handler
- `server/net/websocket.py` (modified) — Added register handler import and registration
- `tests/test_auth.py` (new) — 11 registration and auth tests
