# Story 1.2: Database Engine & Base Models

Status: done

## Story

As a developer,
I want the async database engine and all data models defined,
So that persistence is available for all domain features.

## Acceptance Criteria

1. `server/core/database.py` provides an async engine, async session factory, and `init_db()` function that creates all tables
2. Player model exists with columns: id (Integer PK), username (String(50), unique, indexed), password_hash (String(128)), stats (JSON), inventory (JSON), card_collection (JSON), current_room_id (String(50)), position_x (Integer), position_y (Integer)
3. Room model exists with columns: id (Integer PK), room_key (String(50), unique, indexed), name (String(100)), schema_version (Integer), width (Integer), height (Integer), tile_data (JSON), exits (JSON), objects (JSON), spawn_points (JSON)
4. RoomState model exists with columns: id (Integer PK), room_key (String(50), unique, indexed), mob_states (JSON), dynamic_state (JSON)
5. PlayerObjectState model exists with columns: id (Integer PK), player_id (Integer), room_key (String(50)), object_id (String(50)), state_data (JSON) with unique constraint on (player_id, room_key, object_id)
6. Card model exists with columns: id (Integer PK), card_key (String(50), unique, indexed), name (String(100)), cost (Integer), effects (JSON), description (String(500))
7. SpawnCheckpoint model exists with columns: id (Integer PK), npc_key (String(50)), room_key (String(50)), last_check_at (DateTime), next_check_at (DateTime), currently_spawned (Boolean)
8. Calling `init_db()` creates all tables in SQLite
9. A simple test verifies that `init_db()` creates expected tables and a Player can be inserted and queried

## Tasks / Subtasks

- [x] Task 1: Create `server/core/database.py` (AC: #1, #8)
  - [x] Import async engine and session from SQLAlchemy
  - [x] Use DATABASE_URL from `server.core.config.settings`
  - [x] Create `create_async_engine` with the DATABASE_URL
  - [x] Create `async_sessionmaker` bound to the engine
  - [x] Define declarative `Base` using `DeclarativeBase`
  - [x] Implement `async def init_db()` that runs `Base.metadata.create_all` via `engine.begin()`
  - [x] Implement `async def get_session()` async generator for dependency injection
- [x] Task 2: Create `server/player/models.py` (AC: #2)
  - [x] Define Player model with all specified columns
  - [x] Set `__tablename__ = "players"`
  - [x] Add unique constraint and index on username
  - [x] Use JSON type for stats, inventory, card_collection
  - [x] Set sensible defaults: stats=`{}`, inventory=`{}`, card_collection=`[]`, position_x=0, position_y=0
- [x] Task 3: Create `server/room/models.py` (AC: #3, #4, #5)
  - [x] Define Room model with all specified columns, `__tablename__ = "rooms"`
  - [x] Define RoomState model with all specified columns, `__tablename__ = "room_states"`
  - [x] Define PlayerObjectState model with all specified columns, `__tablename__ = "player_object_states"`
  - [x] Add UniqueConstraint on (player_id, room_key, object_id) for PlayerObjectState
  - [x] Add unique constraint and index on room_key for Room and RoomState
- [x] Task 4: Create `server/combat/cards/models.py` (AC: #6)
  - [x] Define Card model with all specified columns, `__tablename__ = "cards"`
  - [x] Add unique constraint and index on card_key
- [x] Task 5: Create `server/room/spawn_models.py` (AC: #7)
  - [x] Define SpawnCheckpoint model with all specified columns, `__tablename__ = "spawn_checkpoints"`
  - [x] Use DateTime for last_check_at and next_check_at
  - [x] Use Boolean for currently_spawned with default=False
- [x] Task 6: Write test `tests/test_database.py` (AC: #9)
  - [x] Test that init_db() creates all expected tables
  - [x] Test that a Player record can be inserted and queried back
  - [x] Use an in-memory SQLite database for tests (`sqlite+aiosqlite://`)
- [x] Task 7: Verify all models load correctly
  - [x] Run `python -c "from server.core.database import Base, init_db"` to verify imports
  - [x] Run `pytest tests/test_database.py` to verify table creation and CRUD

## Dev Notes

### Architecture Compliance

This story uses the **domain-driven model placement** from architecture.md — models live in their domain packages, NOT in a flat `server/models/` directory.

| Model | File Location |
|-------|--------------|
| Base, engine, session, init_db | `server/core/database.py` |
| Player | `server/player/models.py` |
| Room, RoomState, PlayerObjectState | `server/room/models.py` |
| Card | `server/combat/cards/models.py` |
| SpawnCheckpoint | `server/room/spawn_models.py` |

### SQLAlchemy 2.0 Async Patterns

Use the **SQLAlchemy 2.0 style** (not legacy 1.x patterns):

```python
# database.py — EXACT pattern to follow
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from server.core.config import settings

class Base(DeclarativeBase):
    pass

engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_session():
    async with async_session() as session:
        yield session
```

### Model Definition Pattern

```python
# Example model pattern — use Mapped[] and mapped_column() (SQLAlchemy 2.0 style)
from sqlalchemy import String, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from server.core.database import Base

class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    # ... etc
```

### Critical Import Chain

All model files MUST import `Base` from `server.core.database`. For `init_db()` to see all tables, all model modules must be imported before calling `Base.metadata.create_all`. The recommended approach:

- In `server/core/database.py`, do NOT import models (avoids circular imports)
- In `init_db()` or a dedicated `import_all_models()` helper, import all model modules so they register with Base.metadata
- Pattern: import models inside `init_db()` before `create_all`

```python
async def init_db():
    # Import all models so Base.metadata knows about them
    import server.player.models  # noqa: F401
    import server.room.models  # noqa: F401
    import server.room.spawn_models  # noqa: F401
    import server.combat.cards.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

### JSON Column Defaults

For JSON columns, use `default=dict` or `default=list` (callable factories), NOT `default={}` or `default=[]` (shared mutable default):

```python
stats: Mapped[dict] = mapped_column(JSON, default=dict)
inventory: Mapped[dict] = mapped_column(JSON, default=dict)
card_collection: Mapped[list] = mapped_column(JSON, default=list)
```

### Test Pattern

```python
# tests/test_database.py
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from server.core.database import Base

@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=True)
    async with engine.begin() as conn:
        # Import models so Base knows about them
        import server.player.models  # noqa: F401
        import server.room.models  # noqa: F401
        import server.room.spawn_models  # noqa: F401
        import server.combat.cards.models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()
```

Use `pytest.ini` or `pyproject.toml` to configure pytest-asyncio mode:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

### Anti-Patterns to Avoid

- **DO NOT** create a flat `server/models/` directory — models go in domain packages
- **DO NOT** use `declarative_base()` function — use `class Base(DeclarativeBase)` (SQLAlchemy 2.0)
- **DO NOT** use `Column()` — use `mapped_column()` with `Mapped[]` type hints (SQLAlchemy 2.0)
- **DO NOT** use synchronous engine — use `create_async_engine` and `async_sessionmaker`
- **DO NOT** use `default={}` or `default=[]` for JSON columns — use `default=dict` / `default=list`
- **DO NOT** import models at module level in database.py — import inside `init_db()` to avoid circular imports
- **DO NOT** create any repository classes — that's Story 1.3
- **DO NOT** create any REST endpoints or WebSocket handlers — those are later stories

### Previous Story Intelligence

From Story 1.1 completion notes:
- `build-backend` in pyproject.toml was fixed to `setuptools.build_meta`
- `[tool.setuptools.packages.find]` with `include = ["server*"]` was added
- Virtual environment (`.venv`) is required — activate with `source .venv/bin/activate`
- Config imports via: `from server.core.config import settings`
- DATABASE_URL is already configured: `sqlite+aiosqlite:///{BASE_DIR / 'data' / 'game.db'}`

### Project Structure Notes

- All `__init__.py` files already exist in target directories (server/player/, server/room/, server/combat/cards/, server/core/)
- New files to create: `database.py`, `player/models.py`, `room/models.py`, `room/spawn_models.py`, `combat/cards/models.py`, `tests/test_database.py`
- The `data/` directory already exists for the SQLite database file
- Add `[tool.pytest.ini_options]` to pyproject.toml for asyncio_mode

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#9. Data Models]
- [Source: _bmad-output/planning-artifacts/architecture.md#12. Tech Stack]
- [Source: _bmad-output/planning-artifacts/architecture.md#3.1 Directory Structure]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.2]
- [Source: _bmad-output/implementation-artifacts/1-1-project-scaffolding-and-configuration.md#Dev Agent Record]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References
None

### Completion Notes List
- All 6 models created using SQLAlchemy 2.0 style (DeclarativeBase, Mapped[], mapped_column)
- Domain-driven placement: Player in player/, Room/RoomState/PlayerObjectState in room/, Card in combat/cards/, SpawnCheckpoint in room/
- JSON columns use callable defaults (default=dict, default=list) to avoid shared mutable state
- init_db() imports all model modules inside the function to avoid circular imports
- Added `[tool.pytest.ini_options] asyncio_mode = "auto"` to pyproject.toml for pytest-asyncio
- 2 tests pass: table creation verification and Player CRUD

### File List
- `server/core/database.py` (new) — async engine, Base, session factory, init_db, get_session
- `server/player/models.py` (new) — Player model
- `server/room/models.py` (new) — Room, RoomState, PlayerObjectState models
- `server/room/spawn_models.py` (new) — SpawnCheckpoint model
- `server/combat/cards/models.py` (new) — Card model
- `tests/test_database.py` (new) — database and model tests
- `pyproject.toml` (modified) — added pytest asyncio_mode config
