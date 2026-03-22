# Story 1.3: Persistence Repositories

Status: done

## Story

As a developer,
I want repository classes for Player, Room, and Card data access,
So that domain logic can read/write data without direct SQL.

## Acceptance Criteria

1. `server/player/repo.py` provides `get_by_username`, `get_by_id`, `create`, `save`, `update_position` methods
2. `server/room/repo.py` provides `get_by_key`, `get_state`, `save_state` methods
3. `server/room/provider.py` defines a `RoomProvider` interface with a `load_rooms()` method
4. A `JsonRoomProvider` implementation loads room JSON files from `data/rooms/` into the database
5. `server/combat/cards/card_repo.py` provides `get_by_key`, `get_all`, `load_cards_from_json` methods
6. All repos use async sessions and do not leak connections

## Tasks / Subtasks

- [x] Task 1: Create `server/player/repo.py` (AC: #1, #6)
  - [x] Implement `async def get_by_username(session, username) -> Player | None`
  - [x] Implement `async def get_by_id(session, player_id) -> Player | None`
  - [x] Implement `async def create(session, username, password_hash, starting_room_id) -> Player`
  - [x] Implement `async def save(session, player) -> Player` (merge + commit)
  - [x] Implement `async def update_position(session, player_id, room_key, x, y) -> None`
  - [x] All methods accept `AsyncSession` as first parameter (no session creation inside repo)
- [x] Task 2: Create `server/room/repo.py` (AC: #2, #6)
  - [x] Implement `async def get_by_key(session, room_key) -> Room | None`
  - [x] Implement `async def get_state(session, room_key) -> RoomState | None`
  - [x] Implement `async def save_state(session, room_state) -> RoomState` (merge + commit)
  - [x] Implement `async def upsert_room(session, room) -> Room` for loading rooms from JSON
- [x] Task 3: Create `server/room/provider.py` with RoomProvider and JsonRoomProvider (AC: #3, #4, #6)
  - [x] Define `RoomProvider` as an abstract base class with `async def load_rooms(session) -> list[Room]`
  - [x] Implement `JsonRoomProvider` that reads all `.json` files from `data/rooms/`
  - [x] JsonRoomProvider parses each JSON file into a Room model and upserts into the database
  - [x] JsonRoomProvider uses `settings.DATA_DIR / "rooms"` for the directory path
  - [x] Create a sample room JSON file `data/rooms/test_room.json` for testing
- [x] Task 4: Create `server/combat/cards/card_repo.py` (AC: #5, #6)
  - [x] Implement `async def get_by_key(session, card_key) -> Card | None`
  - [x] Implement `async def get_all(session) -> list[Card]`
  - [x] Implement `async def load_cards_from_json(session, json_path) -> list[Card]`
  - [x] load_cards_from_json reads a JSON file containing a list of card definitions and upserts them
- [x] Task 5: Write tests `tests/test_repos.py` (AC: #1-6)
  - [x] Test PlayerRepo: create, get_by_username, get_by_id, save, update_position
  - [x] Test RoomRepo: upsert_room, get_by_key, get_state, save_state
  - [x] Test JsonRoomProvider: loads room JSON files and inserts into database
  - [x] Test CardRepo: load_cards_from_json, get_by_key, get_all
  - [x] Use in-memory SQLite for all tests
- [x] Task 6: Verify all repos work end-to-end
  - [x] Run `pytest tests/test_repos.py -v` and confirm all pass
  - [x] Run `pytest tests/ -v` to verify no regressions in existing tests

## Dev Notes

### Architecture Compliance

Repos live in their domain packages per architecture.md:

| Repository | File Location |
|-----------|--------------|
| PlayerRepo | `server/player/repo.py` |
| RoomRepo | `server/room/repo.py` |
| RoomProvider / JsonRoomProvider | `server/room/provider.py` |
| CardRepo | `server/combat/cards/card_repo.py` |

### Repository Pattern

Repos are **stateless module-level async functions** that accept an `AsyncSession` as the first parameter. They do NOT create or manage sessions — the caller provides the session. This avoids connection leaks and makes testing straightforward.

```python
# Pattern for all repo functions
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.player.models import Player

async def get_by_username(session: AsyncSession, username: str) -> Player | None:
    result = await session.execute(select(Player).where(Player.username == username))
    return result.scalar_one_or_none()
```

### Session Management

- Repos receive sessions, never create them
- Use `session.execute(select(...))` for queries (SQLAlchemy 2.0 select style)
- Use `session.add()` + `await session.commit()` for inserts
- Use `session.merge()` + `await session.commit()` for upserts
- Use `await session.flush()` to get auto-generated IDs before commit if needed

### RoomProvider Interface Pattern

```python
from abc import ABC, abstractmethod
from sqlalchemy.ext.asyncio import AsyncSession
from server.room.models import Room

class RoomProvider(ABC):
    @abstractmethod
    async def load_rooms(self, session: AsyncSession) -> list[Room]:
        """Load room definitions and persist them to the database."""
        ...
```

### JsonRoomProvider — Room JSON Format

Room JSON files in `data/rooms/` should follow this structure (matching the Room model columns):

```json
{
  "room_key": "town_square",
  "name": "Town Square",
  "schema_version": 1,
  "width": 10,
  "height": 10,
  "tile_data": [[0, 0, 0], [0, 1, 0]],
  "exits": [{"target_room": "dark_cave", "x": 9, "y": 5, "direction": "east"}],
  "objects": [],
  "spawn_points": [{"type": "player", "x": 5, "y": 5}]
}
```

The `room_key` from the JSON is the unique identifier. JsonRoomProvider should upsert (insert or update if room_key exists).

### Card JSON Format

Card JSON files contain a list of card definitions:

```json
[
  {
    "card_key": "fireball",
    "name": "Fireball",
    "cost": 3,
    "effects": [{"type": "damage", "subtype": "fire", "value": 15}],
    "description": "Hurls a ball of fire at the enemy."
  }
]
```

### Test Sample Data

Create minimal test fixtures:
- `data/rooms/test_room.json` — a small 5x5 room for testing JsonRoomProvider
- Test card data can be a temporary JSON file created in the test (use `tmp_path` fixture)

### Existing Code to Use

From Story 1.2 (already implemented):
- `from server.core.database import Base, async_session, engine` — database infrastructure
- `from server.player.models import Player` — Player model with columns: id, username, password_hash, stats, inventory, card_collection, current_room_id, position_x, position_y
- `from server.room.models import Room, RoomState, PlayerObjectState` — Room models
- `from server.combat.cards.models import Card` — Card model with columns: id, card_key, name, cost, effects, description
- `from server.core.config import settings` — settings.DATA_DIR for data directory path
- Test pattern: in-memory SQLite with `create_async_engine("sqlite+aiosqlite://")`, import all models, `Base.metadata.create_all`
- pytest-asyncio configured with `asyncio_mode = "auto"` in pyproject.toml

### Anti-Patterns to Avoid

- **DO NOT** create sessions inside repo functions — accept session as parameter
- **DO NOT** use synchronous SQLAlchemy queries — use `await session.execute(select(...))`
- **DO NOT** use legacy `session.query()` — use `select()` statements (SQLAlchemy 2.0)
- **DO NOT** create any WebSocket handlers, REST endpoints, or domain logic — those are later stories
- **DO NOT** create RoomManager, CombatManager, or any game logic classes — those are Story 1.4+
- **DO NOT** import or reference `PlayerEntity` — that's Story 1.4

### Previous Story Intelligence

From Story 1.2 completion:
- SQLAlchemy 2.0 patterns established: `DeclarativeBase`, `Mapped[]`, `mapped_column()`
- JSON columns use `default=dict` / `default=list` (callable factories)
- `init_db()` imports models inside the function to avoid circular imports
- Virtual environment required: `source .venv/bin/activate`
- All `__init__.py` files already exist in target directories

### Project Structure Notes

- New files to create: `player/repo.py`, `room/repo.py`, `room/provider.py`, `combat/cards/card_repo.py`, `tests/test_repos.py`, `data/rooms/test_room.json`
- All target directories already have `__init__.py` files
- Existing test: `tests/test_database.py` (2 tests) — must not regress

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#3.1 Directory Structure]
- [Source: _bmad-output/planning-artifacts/architecture.md#10. Deferred Features - RoomProvider]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.3]
- [Source: _bmad-output/implementation-artifacts/1-2-database-engine-and-base-models.md#Dev Agent Record]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References
None

### Completion Notes List
- All repos use stateless async functions with session-as-parameter pattern (no connection leaks)
- SQLAlchemy 2.0 select-style queries throughout
- PlayerRepo: 5 methods (get_by_username, get_by_id, create, save, update_position)
- RoomRepo: 4 methods (get_by_key, get_state, save_state, upsert_room)
- RoomProvider ABC + JsonRoomProvider: loads .json files from data/rooms/, upserts via room_repo
- CardRepo: 3 methods (get_by_key, get_all, load_cards_from_json with upsert support)
- Sample test_room.json created in data/rooms/ (5x5 grid with exit and spawn point)
- 11 tests total (2 database + 9 repos), all passing

### File List
- `server/player/repo.py` (new) — Player persistence repository
- `server/room/repo.py` (new) — Room and RoomState persistence repository
- `server/room/provider.py` (new) — RoomProvider ABC and JsonRoomProvider
- `server/combat/cards/card_repo.py` (new) — Card persistence repository
- `data/rooms/test_room.json` (new) — Sample room JSON for testing
- `tests/test_repos.py` (new) — Repository tests (9 tests)
