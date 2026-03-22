# The Ages — Game Server: Full Implementation Plan

## HOW TO USE THIS FILE

1. Quit Claude Code
2. In your terminal:
   ```bash
   cd ~/The\ Ages/
   claude
   ```
3. Then tell Claude:
   ```
   Read /Users/hytseng/The Ages/evennia/THE_AGES_SERVER_PLAN.md and implement everything in it. Create the project at /Users/hytseng/The Ages/the-ages-server/
   ```

---

## Overview

Build a multiplayer room-based dungeon game server with:
- **FastAPI + WebSockets** for real-time game communication
- **SQLite** (via async SQLAlchemy) for persistence
- **Tile-based movement**, turn-based card combat, 20-30 players per room
- **Web API** for card trading, player profiles, custom filters

Target directory: `/Users/hytseng/The Ages/the-ages-server/`

---

## Step 1: Project Scaffolding

### Create directory structure:
```
the-ages-server/
├── server/
│   ├── models/
│   ├── game/
│   ├── net/
│   │   └── handlers/
│   ├── web/
│   └── persistence/
├── data/
│   ├── rooms/
│   └── cards/
├── tests/
├── pyproject.toml
└── run.py
```

### File: `pyproject.toml`
```toml
[project]
name = "the-ages-server"
version = "0.1.0"
description = "The Ages - Multiplayer dungeon game server"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.27.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "aiosqlite>=0.19.0",
    "pydantic>=2.0.0",
    "bcrypt>=4.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.27.0",
]

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"
```

### File: `run.py`
```python
"""Entry point: launch the game server with uvicorn."""
import uvicorn
from server.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "server.app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
```

### File: `server/__init__.py`
Empty file.

### File: `server/config.py`
```python
"""Server configuration settings."""
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True
    DATABASE_URL: str = f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'game.db'}"
    DATA_DIR: Path = BASE_DIR / "data"
    MOB_RESPAWN_SECONDS: int = 60
    COMBAT_TURN_TIMEOUT_SECONDS: int = 30
    MAX_PLAYERS_PER_ROOM: int = 30

settings = Settings()
```

Note: `pydantic-settings` is a separate package. Add `"pydantic-settings>=2.0.0"` to the dependencies list in pyproject.toml.

---

## Step 2: Database Models & Persistence

### File: `server/models/__init__.py`
```python
from server.models.base import Base, get_session, init_db
from server.models.player import Player
from server.models.room import Room
from server.models.room_state import RoomState
from server.models.card import Card
```

### File: `server/models/base.py`
```python
"""SQLAlchemy async engine, session factory, and declarative Base."""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from server.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session
```

### File: `server/models/player.py`
```python
"""Player database model."""
from sqlalchemy import Column, Integer, String, JSON
from server.models.base import Base

class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    stats = Column(JSON, default=lambda: {"hp": 100, "max_hp": 100, "attack": 10, "defense": 5, "xp": 0, "level": 1})
    inventory = Column(JSON, default=list)
    card_collection = Column(JSON, default=list)  # list of card_key strings
    current_room_id = Column(String(50), default="town_square")
    position_x = Column(Integer, default=0)
    position_y = Column(Integer, default=0)
```

### File: `server/models/room.py`
```python
"""Room definition database model."""
from sqlalchemy import Column, Integer, String, JSON
from server.models.base import Base

class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    room_key = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    tile_data = Column(JSON, nullable=False)  # 2D list of tile type strings
    exits = Column(JSON, default=dict)  # {"north": {"target_room": "dark_cave", "entry_x": 5, "entry_y": 0}}
    spawn_points = Column(JSON, default=list)  # [{"x": 5, "y": 5, "type": "player"}, ...]
```

### File: `server/models/room_state.py`
```python
"""Runtime room state (mob alive/dead, dynamic objects)."""
from sqlalchemy import Column, Integer, String, JSON
from server.models.base import Base

class RoomState(Base):
    __tablename__ = "room_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    room_key = Column(String(50), unique=True, nullable=False, index=True)
    mob_states = Column(JSON, default=dict)  # {"mob_id": {"alive": true, "respawn_at": null}}
    dynamic_state = Column(JSON, default=dict)  # extensible for future use
```

### File: `server/models/card.py`
```python
"""Card definition database model."""
from sqlalchemy import Column, Integer, String, JSON
from server.models.base import Base

class Card(Base):
    __tablename__ = "cards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    card_key = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    cost = Column(Integer, default=1)
    effect_type = Column(String(30), nullable=False)  # damage, heal, shield, draw, poison
    effect_value = Column(Integer, default=0)
    description = Column(String(500), default="")
```

### File: `server/persistence/__init__.py`
Empty file.

### File: `server/persistence/player_repo.py`
```python
"""Player data persistence operations."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from server.models.player import Player

class PlayerRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_username(self, username: str) -> Player | None:
        result = await self.session.execute(select(Player).where(Player.username == username))
        return result.scalar_one_or_none()

    async def get_by_id(self, player_id: int) -> Player | None:
        result = await self.session.execute(select(Player).where(Player.id == player_id))
        return result.scalar_one_or_none()

    async def create(self, username: str, password_hash: str) -> Player:
        player = Player(username=username, password_hash=password_hash)
        self.session.add(player)
        await self.session.commit()
        await self.session.refresh(player)
        return player

    async def save(self, player: Player) -> None:
        self.session.add(player)
        await self.session.commit()

    async def update_position(self, player_id: int, room_key: str, x: int, y: int) -> None:
        player = await self.get_by_id(player_id)
        if player:
            player.current_room_id = room_key
            player.position_x = x
            player.position_y = y
            await self.session.commit()
```

### File: `server/persistence/room_repo.py`
```python
"""Room data persistence operations."""
import json
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from server.models.room import Room
from server.models.room_state import RoomState
from server.config import settings

class RoomRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_key(self, room_key: str) -> Room | None:
        result = await self.session.execute(select(Room).where(Room.room_key == room_key))
        return result.scalar_one_or_none()

    async def get_state(self, room_key: str) -> RoomState | None:
        result = await self.session.execute(select(RoomState).where(RoomState.room_key == room_key))
        return result.scalar_one_or_none()

    async def save_state(self, room_key: str, mob_states: dict) -> None:
        state = await self.get_state(room_key)
        if state:
            state.mob_states = mob_states
        else:
            state = RoomState(room_key=room_key, mob_states=mob_states)
            self.session.add(state)
        await self.session.commit()

    async def load_rooms_from_json(self) -> None:
        """Load room definitions from JSON data files into the database."""
        rooms_dir = settings.DATA_DIR / "rooms"
        if not rooms_dir.exists():
            return
        for room_file in rooms_dir.glob("*.json"):
            with open(room_file) as f:
                data = json.load(f)
            room_key = room_file.stem
            existing = await self.get_by_key(room_key)
            if existing:
                continue
            room = Room(
                room_key=room_key,
                name=data["name"],
                width=data["width"],
                height=data["height"],
                tile_data=data["tiles"],
                exits=data.get("exits", {}),
                spawn_points=data.get("spawn_points", []),
            )
            self.session.add(room)
        await self.session.commit()
```

### File: `server/persistence/card_repo.py`
```python
"""Card data persistence operations."""
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from server.models.card import Card
from server.config import settings

class CardRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_key(self, card_key: str) -> Card | None:
        result = await self.session.execute(select(Card).where(Card.card_key == card_key))
        return result.scalar_one_or_none()

    async def get_all(self) -> list[Card]:
        result = await self.session.execute(select(Card))
        return list(result.scalars().all())

    async def load_cards_from_json(self) -> None:
        """Load card definitions from JSON data files into the database."""
        cards_dir = settings.DATA_DIR / "cards"
        if not cards_dir.exists():
            return
        for card_file in cards_dir.glob("*.json"):
            with open(card_file) as f:
                data = json.load(f)
            for card_data in data.get("cards", []):
                existing = await self.get_by_key(card_data["card_key"])
                if existing:
                    continue
                card = Card(
                    card_key=card_data["card_key"],
                    name=card_data["name"],
                    cost=card_data.get("cost", 1),
                    effect_type=card_data["effect_type"],
                    effect_value=card_data.get("effect_value", 0),
                    description=card_data.get("description", ""),
                )
                self.session.add(card)
        await self.session.commit()
```

---

## Step 3: Core Game Logic — Room & Tiles

### File: `server/game/__init__.py`
Empty file.

### File: `server/game/tile.py`
```python
"""Tile types and properties for the room grid."""
from enum import Enum
from dataclasses import dataclass, field
from typing import Any

class TileType(str, Enum):
    FLOOR = "floor"
    WALL = "wall"
    EXIT = "exit"
    MOB_SPAWN = "mob_spawn"
    COMBAT = "combat"

WALKABLE_TILES = {TileType.FLOOR, TileType.EXIT, TileType.MOB_SPAWN}

@dataclass
class Tile:
    type: TileType
    walkable: bool = True
    entity_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.walkable = self.type in WALKABLE_TILES

    def is_occupied(self) -> bool:
        return self.entity_id is not None
```

### File: `server/game/entity.py`
```python
"""Entity types: players and mobs in the game world."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import uuid

class EntityType(str, Enum):
    PLAYER = "player"
    MOB = "mob"

@dataclass
class Entity:
    id: str
    name: str
    x: int
    y: int
    entity_type: EntityType

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "x": self.x, "y": self.y, "type": self.entity_type.value}

@dataclass
class PlayerEntity(Entity):
    player_db_id: int = 0
    stats: dict[str, Any] = field(default_factory=lambda: {"hp": 100, "max_hp": 100, "attack": 10, "defense": 5})
    in_combat: bool = False

    def __post_init__(self):
        self.entity_type = EntityType.PLAYER

@dataclass
class MobEntity(Entity):
    mob_type: str = "slime"
    is_alive: bool = True
    respawn_at: float | None = None
    loot_table: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=lambda: {"hp": 50, "max_hp": 50, "attack": 8, "defense": 3})

    def __post_init__(self):
        self.entity_type = EntityType.MOB
```

### File: `server/game/room.py`
```python
"""Room instance: tile grid, entities, movement validation."""
from __future__ import annotations
from typing import Any, Callable, Coroutine
from server.game.tile import Tile, TileType, WALKABLE_TILES
from server.game.entity import Entity, PlayerEntity, MobEntity, EntityType

DIRECTION_DELTAS = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}

class Room:
    def __init__(self, room_key: str, name: str, width: int, height: int,
                 tile_data: list[list[str]], exits: dict, spawn_points: list[dict]):
        self.room_key = room_key
        self.name = name
        self.width = width
        self.height = height
        self.exits = exits  # {"north": {"target_room": "...", "entry_x": 0, "entry_y": 0}}
        self.spawn_points = spawn_points
        self.entities: dict[str, Entity] = {}
        self._broadcast_fn: Callable | None = None

        # Build tile grid from string data
        self.tiles: list[list[Tile]] = []
        for row in tile_data:
            tile_row = []
            for cell in row:
                tile_row.append(Tile(type=TileType(cell)))
            self.tiles.append(tile_row)

    def set_broadcast_fn(self, fn: Callable):
        """Set the function used to broadcast messages to players in this room."""
        self._broadcast_fn = fn

    def get_tile(self, x: int, y: int) -> Tile | None:
        if 0 <= y < self.height and 0 <= x < self.width:
            return self.tiles[y][x]
        return None

    def get_entities_at(self, x: int, y: int) -> list[Entity]:
        return [e for e in self.entities.values() if e.x == x and e.y == y]

    def get_player_spawn(self) -> tuple[int, int]:
        for sp in self.spawn_points:
            if sp.get("type") == "player":
                return sp["x"], sp["y"]
        return 0, 0

    def add_entity(self, entity: Entity) -> bool:
        tile = self.get_tile(entity.x, entity.y)
        if tile is None:
            return False
        self.entities[entity.id] = entity
        return True

    def remove_entity(self, entity_id: str) -> Entity | None:
        return self.entities.pop(entity_id, None)

    def move_entity(self, entity_id: str, direction: str) -> dict[str, Any]:
        """Move an entity in a direction. Returns result dict with success/failure info."""
        entity = self.entities.get(entity_id)
        if entity is None:
            return {"success": False, "error": "Entity not found"}

        delta = DIRECTION_DELTAS.get(direction)
        if delta is None:
            return {"success": False, "error": f"Invalid direction: {direction}"}

        new_x = entity.x + delta[0]
        new_y = entity.y + delta[1]
        tile = self.get_tile(new_x, new_y)

        if tile is None:
            return {"success": False, "error": "Out of bounds"}
        if not tile.walkable:
            return {"success": False, "error": "Tile not walkable"}

        # Check for exit tiles
        if tile.type == TileType.EXIT:
            exit_info = self._find_exit_at(new_x, new_y)
            if exit_info:
                return {
                    "success": True,
                    "exit": True,
                    "target_room": exit_info["target_room"],
                    "entry_x": exit_info["entry_x"],
                    "entry_y": exit_info["entry_y"],
                }

        # Check for mob encounter
        mobs_at = [e for e in self.get_entities_at(new_x, new_y) if isinstance(e, MobEntity) and e.is_alive]

        entity.x = new_x
        entity.y = new_y

        result: dict[str, Any] = {"success": True, "x": new_x, "y": new_y}
        if mobs_at:
            result["mob_encounter"] = mobs_at[0].id
        return result

    def _find_exit_at(self, x: int, y: int) -> dict | None:
        for exit_dir, exit_data in self.exits.items():
            if exit_data.get("x") == x and exit_data.get("y") == y:
                return exit_data
        return None

    def get_state(self) -> dict:
        """Return a serializable snapshot of the room."""
        return {
            "room_key": self.room_key,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "tiles": [[t.type.value for t in row] for row in self.tiles],
            "entities": {eid: e.to_dict() for eid, e in self.entities.items()},
            "exits": self.exits,
        }

    def get_player_ids(self) -> list[str]:
        return [eid for eid, e in self.entities.items() if e.entity_type == EntityType.PLAYER]
```

### File: `server/game/room_manager.py`
```python
"""Manages active rooms: loading, unloading, transfers."""
from __future__ import annotations
from server.game.room import Room
from server.game.entity import Entity

class RoomManager:
    def __init__(self):
        self.active_rooms: dict[str, Room] = {}

    def get_room(self, room_key: str) -> Room | None:
        return self.active_rooms.get(room_key)

    def load_room(self, room_key: str, name: str, width: int, height: int,
                  tile_data: list[list[str]], exits: dict, spawn_points: list[dict]) -> Room:
        if room_key in self.active_rooms:
            return self.active_rooms[room_key]
        room = Room(room_key, name, width, height, tile_data, exits, spawn_points)
        self.active_rooms[room_key] = room
        return room

    def unload_room(self, room_key: str) -> None:
        self.active_rooms.pop(room_key, None)

    def transfer_entity(self, entity: Entity, from_room_key: str, to_room_key: str,
                        entry_x: int, entry_y: int) -> bool:
        from_room = self.get_room(from_room_key)
        to_room = self.get_room(to_room_key)
        if from_room is None or to_room is None:
            return False
        from_room.remove_entity(entity.id)
        entity.x = entry_x
        entity.y = entry_y
        return to_room.add_entity(entity)
```

---

## Step 4: Networking — WebSocket & Message Routing

### File: `server/net/__init__.py`
Empty file.

### File: `server/net/handlers/__init__.py`
Empty file.

### File: `server/net/protocol.py`
```python
"""Message schema definitions for client-server communication."""
from pydantic import BaseModel
from typing import Any

# --- Client → Server ---

class LoginMessage(BaseModel):
    action: str = "login"
    username: str
    password: str

class RegisterMessage(BaseModel):
    action: str = "register"
    username: str
    password: str

class MoveMessage(BaseModel):
    action: str = "move"
    direction: str  # up, down, left, right

class ChatMessage(BaseModel):
    action: str = "chat"
    message: str
    whisper_to: str | None = None

class InteractMessage(BaseModel):
    action: str = "interact"
    target_id: str

class PlayCardMessage(BaseModel):
    action: str = "play_card"
    card_key: str
    target_id: str | None = None

class PassTurnMessage(BaseModel):
    action: str = "pass_turn"

class FleeMessage(BaseModel):
    action: str = "flee"

# --- Server → Client ---

def server_message(msg_type: str, **kwargs) -> dict:
    return {"type": msg_type, **kwargs}

def error_message(detail: str) -> dict:
    return server_message("error", detail=detail)

def room_state_message(room_state: dict) -> dict:
    return server_message("room_state", **room_state)

def entity_moved_message(entity_id: str, x: int, y: int) -> dict:
    return server_message("entity_moved", entity_id=entity_id, x=x, y=y)

def entity_entered_message(entity: dict) -> dict:
    return server_message("entity_entered", entity=entity)

def entity_left_message(entity_id: str) -> dict:
    return server_message("entity_left", entity_id=entity_id)

def chat_message_out(sender: str, message: str, whisper: bool = False) -> dict:
    return server_message("chat", sender=sender, message=message, whisper=whisper)

def combat_start_message(instance_id: str, participants: list, mob: dict) -> dict:
    return server_message("combat_start", instance_id=instance_id, participants=participants, mob=mob)

def combat_turn_message(instance_id: str, current_player: str, hand: list, mob_hp: int, player_hps: dict) -> dict:
    return server_message("combat_turn", instance_id=instance_id, current_player=current_player,
                          hand=hand, mob_hp=mob_hp, player_hps=player_hps)

def combat_end_message(instance_id: str, victory: bool, rewards: dict | None = None) -> dict:
    return server_message("combat_end", instance_id=instance_id, victory=victory, rewards=rewards or {})

def login_success_message(player_id: int, username: str) -> dict:
    return server_message("login_success", player_id=player_id, username=username)
```

### File: `server/net/connection_manager.py`
```python
"""Track WebSocket connections and map to players."""
from __future__ import annotations
import json
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.connections: dict[str, WebSocket] = {}  # player_entity_id → WebSocket
        self.ws_to_player: dict[int, str] = {}  # id(ws) → player_entity_id

    async def connect(self, websocket: WebSocket, player_entity_id: str) -> None:
        self.connections[player_entity_id] = websocket
        self.ws_to_player[id(websocket)] = player_entity_id

    def disconnect(self, websocket: WebSocket) -> str | None:
        player_id = self.ws_to_player.pop(id(websocket), None)
        if player_id:
            self.connections.pop(player_id, None)
        return player_id

    def get_player_id(self, websocket: WebSocket) -> str | None:
        return self.ws_to_player.get(id(websocket))

    def get_websocket(self, player_entity_id: str) -> WebSocket | None:
        return self.connections.get(player_entity_id)

    async def send_to_player(self, player_entity_id: str, message: dict) -> None:
        ws = self.connections.get(player_entity_id)
        if ws:
            await ws.send_json(message)

    async def broadcast_to_room(self, player_ids: list[str], message: dict, exclude: str | None = None) -> None:
        for pid in player_ids:
            if pid != exclude:
                await self.send_to_player(pid, message)
```

### File: `server/net/message_router.py`
```python
"""Route incoming JSON messages to appropriate handlers."""
from __future__ import annotations
from fastapi import WebSocket
from server.net.protocol import error_message

class MessageRouter:
    def __init__(self):
        self._handlers: dict[str, any] = {}

    def register(self, action: str, handler):
        self._handlers[action] = handler

    async def route(self, websocket: WebSocket, data: dict) -> None:
        action = data.get("action")
        if not action:
            await websocket.send_json(error_message("Missing 'action' field"))
            return

        handler = self._handlers.get(action)
        if handler is None:
            await websocket.send_json(error_message(f"Unknown action: {action}"))
            return

        await handler(websocket, data)
```

### File: `server/net/handlers/auth.py`
```python
"""Login and registration handlers."""
from __future__ import annotations
import bcrypt
from fastapi import WebSocket
from server.net.protocol import error_message, login_success_message, room_state_message
from server.game.entity import PlayerEntity

async def handle_login(websocket: WebSocket, data: dict, *, game) -> None:
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        await websocket.send_json(error_message("Username and password required"))
        return

    async with game.db_session() as session:
        from server.persistence.player_repo import PlayerRepo
        repo = PlayerRepo(session)
        player = await repo.get_by_username(username)

        if player is None:
            await websocket.send_json(error_message("Invalid username or password"))
            return

        if not bcrypt.checkpw(password.encode(), player.password_hash.encode()):
            await websocket.send_json(error_message("Invalid username or password"))
            return

        # Create player entity
        entity_id = f"player_{player.id}"
        entity = PlayerEntity(
            id=entity_id,
            name=player.username,
            x=player.position_x,
            y=player.position_y,
            entity_type="player",
            player_db_id=player.id,
            stats=player.stats or {},
        )

        # Connect and place in room
        await game.connection_manager.connect(websocket, entity_id)
        room = game.room_manager.get_room(player.current_room_id)
        if room is None:
            room = await game.load_room(player.current_room_id)
        if room is None:
            await websocket.send_json(error_message("Room not found"))
            return

        room.add_entity(entity)
        game.player_entities[entity_id] = {"entity": entity, "room_key": player.current_room_id, "db_id": player.id}

        await websocket.send_json(login_success_message(player.id, player.username))
        await websocket.send_json(room_state_message(room.get_state()))

        # Notify others
        from server.net.protocol import entity_entered_message
        await game.connection_manager.broadcast_to_room(
            room.get_player_ids(), entity_entered_message(entity.to_dict()), exclude=entity_id
        )


async def handle_register(websocket: WebSocket, data: dict, *, game) -> None:
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or len(username) < 3:
        await websocket.send_json(error_message("Username must be at least 3 characters"))
        return
    if not password or len(password) < 6:
        await websocket.send_json(error_message("Password must be at least 6 characters"))
        return

    async with game.db_session() as session:
        from server.persistence.player_repo import PlayerRepo
        repo = PlayerRepo(session)

        existing = await repo.get_by_username(username)
        if existing:
            await websocket.send_json(error_message("Username already taken"))
            return

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        player = await repo.create(username, hashed)

        await websocket.send_json(login_success_message(player.id, player.username))
```

### File: `server/net/handlers/movement.py`
```python
"""Movement and room transition handlers."""
from __future__ import annotations
from fastapi import WebSocket
from server.net.protocol import error_message, entity_moved_message, entity_left_message, entity_entered_message, room_state_message

async def handle_move(websocket: WebSocket, data: dict, *, game) -> None:
    entity_id = game.connection_manager.get_player_id(websocket)
    if not entity_id:
        await websocket.send_json(error_message("Not logged in"))
        return

    player_info = game.player_entities.get(entity_id)
    if not player_info:
        await websocket.send_json(error_message("Player not found"))
        return

    entity = player_info["entity"]
    if entity.in_combat:
        await websocket.send_json(error_message("Cannot move while in combat"))
        return

    room = game.room_manager.get_room(player_info["room_key"])
    if not room:
        await websocket.send_json(error_message("Room not found"))
        return

    direction = data.get("direction", "")
    result = room.move_entity(entity_id, direction)

    if not result["success"]:
        await websocket.send_json(error_message(result["error"]))
        return

    if result.get("exit"):
        # Room transition
        target_key = result["target_room"]
        target_room = game.room_manager.get_room(target_key)
        if not target_room:
            target_room = await game.load_room(target_key)
        if not target_room:
            await websocket.send_json(error_message("Exit leads nowhere"))
            return

        # Remove from old room, notify
        room.remove_entity(entity_id)
        await game.connection_manager.broadcast_to_room(
            room.get_player_ids(), entity_left_message(entity_id)
        )

        # Add to new room
        entity.x = result["entry_x"]
        entity.y = result["entry_y"]
        target_room.add_entity(entity)
        player_info["room_key"] = target_key

        # Save position
        await game.save_player_position(entity_id)

        # Send new room state to player
        await websocket.send_json(room_state_message(target_room.get_state()))

        # Notify new room
        await game.connection_manager.broadcast_to_room(
            target_room.get_player_ids(), entity_entered_message(entity.to_dict()), exclude=entity_id
        )
        return

    # Normal movement
    await game.connection_manager.broadcast_to_room(
        room.get_player_ids(), entity_moved_message(entity_id, result["x"], result["y"])
    )

    # Check for mob encounter
    if result.get("mob_encounter"):
        await game.start_combat(entity_id, result["mob_encounter"], player_info["room_key"])
```

### File: `server/net/handlers/chat.py`
```python
"""Chat message handlers."""
from __future__ import annotations
from fastapi import WebSocket
from server.net.protocol import error_message, chat_message_out

async def handle_chat(websocket: WebSocket, data: dict, *, game) -> None:
    entity_id = game.connection_manager.get_player_id(websocket)
    if not entity_id:
        await websocket.send_json(error_message("Not logged in"))
        return

    player_info = game.player_entities.get(entity_id)
    if not player_info:
        return

    message = data.get("message", "").strip()
    if not message:
        return

    entity = player_info["entity"]
    whisper_to = data.get("whisper_to")

    if whisper_to:
        # Whisper to specific player
        target_id = f"player_{whisper_to}" if not whisper_to.startswith("player_") else whisper_to
        await game.connection_manager.send_to_player(
            target_id, chat_message_out(entity.name, message, whisper=True)
        )
        await websocket.send_json(chat_message_out(entity.name, message, whisper=True))
    else:
        # Broadcast to room
        room = game.room_manager.get_room(player_info["room_key"])
        if room:
            await game.connection_manager.broadcast_to_room(
                room.get_player_ids(), chat_message_out(entity.name, message)
            )
```

### File: `server/net/handlers/combat.py`
```python
"""Combat action handlers: play card, pass turn, flee."""
from __future__ import annotations
from fastapi import WebSocket
from server.net.protocol import error_message

async def handle_play_card(websocket: WebSocket, data: dict, *, game) -> None:
    entity_id = game.connection_manager.get_player_id(websocket)
    if not entity_id:
        await websocket.send_json(error_message("Not logged in"))
        return

    player_info = game.player_entities.get(entity_id)
    if not player_info:
        return

    entity = player_info["entity"]
    if not entity.in_combat:
        await websocket.send_json(error_message("Not in combat"))
        return

    instance = game.combat_manager.get_instance_for_player(entity_id)
    if not instance:
        await websocket.send_json(error_message("Combat instance not found"))
        return

    card_key = data.get("card_key")
    if not card_key:
        await websocket.send_json(error_message("No card specified"))
        return

    result = instance.play_card(entity_id, card_key)
    if not result["success"]:
        await websocket.send_json(error_message(result["error"]))
        return

    # Broadcast combat update
    await game.broadcast_combat_state(instance)

    if instance.is_finished:
        await game.end_combat(instance)


async def handle_pass_turn(websocket: WebSocket, data: dict, *, game) -> None:
    entity_id = game.connection_manager.get_player_id(websocket)
    if not entity_id:
        await websocket.send_json(error_message("Not logged in"))
        return

    player_info = game.player_entities.get(entity_id)
    if not player_info or not player_info["entity"].in_combat:
        await websocket.send_json(error_message("Not in combat"))
        return

    instance = game.combat_manager.get_instance_for_player(entity_id)
    if not instance:
        return

    result = instance.pass_turn(entity_id)
    if not result["success"]:
        await websocket.send_json(error_message(result["error"]))
        return

    await game.broadcast_combat_state(instance)

    if instance.is_finished:
        await game.end_combat(instance)


async def handle_flee(websocket: WebSocket, data: dict, *, game) -> None:
    entity_id = game.connection_manager.get_player_id(websocket)
    if not entity_id:
        await websocket.send_json(error_message("Not logged in"))
        return

    player_info = game.player_entities.get(entity_id)
    if not player_info or not player_info["entity"].in_combat:
        await websocket.send_json(error_message("Not in combat"))
        return

    instance = game.combat_manager.get_instance_for_player(entity_id)
    if not instance:
        return

    instance.remove_participant(entity_id)
    player_info["entity"].in_combat = False

    await websocket.send_json({"type": "combat_fled"})

    if instance.is_finished or len(instance.participants) == 0:
        await game.end_combat(instance)
    else:
        await game.broadcast_combat_state(instance)
```

### File: `server/net/handlers/inventory.py`
```python
"""Inventory handlers (placeholder for future expansion)."""
from __future__ import annotations
from fastapi import WebSocket
from server.net.protocol import error_message

async def handle_inventory(websocket: WebSocket, data: dict, *, game) -> None:
    entity_id = game.connection_manager.get_player_id(websocket)
    if not entity_id:
        await websocket.send_json(error_message("Not logged in"))
        return

    player_info = game.player_entities.get(entity_id)
    if not player_info:
        return

    # Fetch from DB
    async with game.db_session() as session:
        from server.persistence.player_repo import PlayerRepo
        repo = PlayerRepo(session)
        player = await repo.get_by_id(player_info["db_id"])
        if player:
            await websocket.send_json({
                "type": "inventory",
                "inventory": player.inventory or [],
                "cards": player.card_collection or [],
            })
```

---

## Step 5: Core Game Logic — Combat

### File: `server/game/card.py`
```python
"""Card definitions, effects, and hand management."""
from __future__ import annotations
from dataclasses import dataclass, field
import random

@dataclass
class CardDef:
    card_key: str
    name: str
    cost: int
    effect_type: str  # damage, heal, shield, draw, poison
    effect_value: int
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "card_key": self.card_key, "name": self.name, "cost": self.cost,
            "effect_type": self.effect_type, "effect_value": self.effect_value,
            "description": self.description,
        }

class CardHand:
    def __init__(self, deck: list[CardDef], hand_size: int = 5):
        self.deck = list(deck)
        random.shuffle(self.deck)
        self.hand: list[CardDef] = []
        self.discard: list[CardDef] = []
        self.hand_size = hand_size
        self.draw_initial()

    def draw_initial(self):
        for _ in range(self.hand_size):
            self.draw()

    def draw(self) -> CardDef | None:
        if not self.deck:
            # Reshuffle discard into deck
            self.deck = list(self.discard)
            self.discard.clear()
            random.shuffle(self.deck)
        if not self.deck:
            return None
        card = self.deck.pop()
        self.hand.append(card)
        return card

    def play(self, card_key: str) -> CardDef | None:
        for i, card in enumerate(self.hand):
            if card.card_key == card_key:
                played = self.hand.pop(i)
                self.discard.append(played)
                self.draw()
                return played
        return None

    def get_hand_dicts(self) -> list[dict]:
        return [c.to_dict() for c in self.hand]
```

### File: `server/game/combat_instance.py`
```python
"""Single combat instance: participants, turns, card resolution."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import uuid
from server.game.card import CardDef, CardHand
from server.game.entity import PlayerEntity, MobEntity

class CombatInstance:
    def __init__(self, instance_id: str, mob: MobEntity, card_defs: list[CardDef]):
        self.instance_id = instance_id
        self.mob = mob
        self.mob_hp = mob.stats.get("max_hp", 50)
        self.mob_max_hp = self.mob_hp
        self.participants: list[str] = []  # entity IDs
        self.player_hands: dict[str, CardHand] = {}
        self.player_hps: dict[str, int] = {}
        self.player_shields: dict[str, int] = {}
        self.turn_order: list[str] = []
        self.current_turn_index: int = 0
        self.is_finished: bool = False
        self.victory: bool = False
        self.card_defs = card_defs
        self.countdown_task = None

    def add_participant(self, entity: PlayerEntity) -> None:
        self.participants.append(entity.id)
        self.player_hps[entity.id] = entity.stats.get("hp", 100)
        self.player_shields[entity.id] = 0
        # Give each player a hand from the card defs
        self.player_hands[entity.id] = CardHand(list(self.card_defs))
        self.turn_order.append(entity.id)
        entity.in_combat = True

    def remove_participant(self, entity_id: str) -> None:
        if entity_id in self.participants:
            self.participants.remove(entity_id)
        if entity_id in self.turn_order:
            idx = self.turn_order.index(entity_id)
            self.turn_order.remove(entity_id)
            if self.current_turn_index >= len(self.turn_order) and self.turn_order:
                self.current_turn_index = 0

    @property
    def current_player(self) -> str | None:
        if not self.turn_order:
            return None
        return self.turn_order[self.current_turn_index % len(self.turn_order)]

    def play_card(self, entity_id: str, card_key: str) -> dict:
        if entity_id != self.current_player:
            return {"success": False, "error": "Not your turn"}

        hand = self.player_hands.get(entity_id)
        if not hand:
            return {"success": False, "error": "No hand found"}

        card = hand.play(card_key)
        if not card:
            return {"success": False, "error": "Card not in hand"}

        # Resolve effect
        self._resolve_card(entity_id, card)

        # Check victory/defeat
        if self.mob_hp <= 0:
            self.is_finished = True
            self.victory = True
            return {"success": True, "resolved": True}

        if all(hp <= 0 for hp in self.player_hps.values()):
            self.is_finished = True
            self.victory = False
            return {"success": True, "resolved": True}

        # Advance turn
        self._advance_turn()
        return {"success": True}

    def pass_turn(self, entity_id: str) -> dict:
        if entity_id != self.current_player:
            return {"success": False, "error": "Not your turn"}

        # Mob attacks passing player
        self._mob_attack(entity_id)

        if all(hp <= 0 for hp in self.player_hps.values()):
            self.is_finished = True
            self.victory = False
            return {"success": True, "resolved": True}

        self._advance_turn()
        return {"success": True}

    def _resolve_card(self, player_id: str, card: CardDef) -> None:
        if card.effect_type == "damage":
            self.mob_hp = max(0, self.mob_hp - card.effect_value)
        elif card.effect_type == "heal":
            self.player_hps[player_id] = min(
                100, self.player_hps[player_id] + card.effect_value
            )
        elif card.effect_type == "shield":
            self.player_shields[player_id] += card.effect_value
        elif card.effect_type == "poison":
            self.mob_hp = max(0, self.mob_hp - card.effect_value)
        elif card.effect_type == "draw":
            hand = self.player_hands.get(player_id)
            if hand:
                for _ in range(card.effect_value):
                    hand.draw()

    def _mob_attack(self, target_id: str) -> None:
        attack = self.mob.stats.get("attack", 8)
        shield = self.player_shields.get(target_id, 0)
        if shield > 0:
            absorbed = min(shield, attack)
            self.player_shields[target_id] -= absorbed
            attack -= absorbed
        if attack > 0:
            self.player_hps[target_id] = max(0, self.player_hps[target_id] - attack)

    def _advance_turn(self) -> None:
        self.current_turn_index = (self.current_turn_index + 1) % len(self.turn_order)
        # If it wraps around, mob attacks a random player
        if self.current_turn_index == 0 and self.turn_order:
            import random
            target = random.choice(self.turn_order)
            self._mob_attack(target)

    def get_state(self) -> dict:
        return {
            "instance_id": self.instance_id,
            "mob": {"name": self.mob.name, "hp": self.mob_hp, "max_hp": self.mob_max_hp},
            "current_player": self.current_player,
            "player_hps": dict(self.player_hps),
            "player_shields": dict(self.player_shields),
            "is_finished": self.is_finished,
            "victory": self.victory,
        }

    def get_hand_for_player(self, entity_id: str) -> list[dict]:
        hand = self.player_hands.get(entity_id)
        return hand.get_hand_dicts() if hand else []
```

### File: `server/game/combat_manager.py`
```python
"""Manages active combat instances."""
from __future__ import annotations
import uuid
from server.game.combat_instance import CombatInstance
from server.game.entity import PlayerEntity, MobEntity
from server.game.card import CardDef

class CombatManager:
    def __init__(self):
        self.instances: dict[str, CombatInstance] = {}
        self.player_to_instance: dict[str, str] = {}  # entity_id → instance_id

    def create_instance(self, mob: MobEntity, card_defs: list[CardDef]) -> CombatInstance:
        instance_id = str(uuid.uuid4())[:8]
        instance = CombatInstance(instance_id, mob, card_defs)
        self.instances[instance_id] = instance
        return instance

    def add_player_to_instance(self, instance_id: str, entity: PlayerEntity) -> bool:
        instance = self.instances.get(instance_id)
        if not instance:
            return False
        instance.add_participant(entity)
        self.player_to_instance[entity.id] = instance_id
        return True

    def get_instance(self, instance_id: str) -> CombatInstance | None:
        return self.instances.get(instance_id)

    def get_instance_for_player(self, entity_id: str) -> CombatInstance | None:
        instance_id = self.player_to_instance.get(entity_id)
        if instance_id:
            return self.instances.get(instance_id)
        return None

    def remove_instance(self, instance_id: str) -> None:
        instance = self.instances.pop(instance_id, None)
        if instance:
            for pid in instance.participants:
                self.player_to_instance.pop(pid, None)
```

### File: `server/game/timer_service.py`
```python
"""Async timer service for mob respawns and combat countdowns."""
from __future__ import annotations
import asyncio
from typing import Callable, Coroutine, Any

class TimerService:
    def __init__(self):
        self.tasks: dict[str, asyncio.Task] = {}

    def schedule(self, timer_id: str, delay: float, callback: Callable[[], Coroutine]) -> None:
        if timer_id in self.tasks:
            self.tasks[timer_id].cancel()

        async def _run():
            await asyncio.sleep(delay)
            await callback()
            self.tasks.pop(timer_id, None)

        self.tasks[timer_id] = asyncio.create_task(_run())

    def cancel(self, timer_id: str) -> None:
        task = self.tasks.pop(timer_id, None)
        if task:
            task.cancel()

    def cancel_all(self) -> None:
        for task in self.tasks.values():
            task.cancel()
        self.tasks.clear()
```

---

## Step 6: Main App (ties everything together)

### File: `server/app.py`
```python
"""FastAPI app: startup/shutdown, WebSocket endpoint, game orchestration."""
from __future__ import annotations
import asyncio
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from server.config import settings
from server.models.base import init_db, async_session_factory
from server.game.room_manager import RoomManager
from server.game.combat_manager import CombatManager
from server.game.timer_service import TimerService
from server.game.card import CardDef
from server.game.entity import MobEntity
from server.net.connection_manager import ConnectionManager
from server.net.message_router import MessageRouter
from server.net.protocol import (
    error_message, combat_start_message, combat_turn_message, combat_end_message,
    entity_left_message,
)

class Game:
    """Central game orchestrator — holds all managers and state."""

    def __init__(self):
        self.room_manager = RoomManager()
        self.combat_manager = CombatManager()
        self.connection_manager = ConnectionManager()
        self.timer_service = TimerService()
        self.router = MessageRouter()
        self.player_entities: dict = {}  # entity_id → {"entity", "room_key", "db_id"}
        self.card_defs: list[CardDef] = []

    @asynccontextmanager
    async def db_session(self):
        async with async_session_factory() as session:
            yield session

    async def startup(self):
        await init_db()

        # Load rooms from JSON into DB, then into memory
        async with self.db_session() as session:
            from server.persistence.room_repo import RoomRepo
            repo = RoomRepo(session)
            await repo.load_rooms_from_json()

            # Load all rooms into memory
            from server.models.room import Room as RoomModel
            from sqlalchemy import select
            result = await session.execute(select(RoomModel))
            for room_row in result.scalars().all():
                room = self.room_manager.load_room(
                    room_key=room_row.room_key,
                    name=room_row.name,
                    width=room_row.width,
                    height=room_row.height,
                    tile_data=room_row.tile_data,
                    exits=room_row.exits or {},
                    spawn_points=room_row.spawn_points or [],
                )
                # Spawn mobs from mob_spawn tiles
                self._spawn_room_mobs(room)

        # Load card definitions
        async with self.db_session() as session:
            from server.persistence.card_repo import CardRepo
            repo = CardRepo(session)
            await repo.load_cards_from_json()
            cards = await repo.get_all()
            self.card_defs = [
                CardDef(c.card_key, c.name, c.cost, c.effect_type, c.effect_value, c.description)
                for c in cards
            ]

        # Register message handlers
        self._register_handlers()

    def _spawn_room_mobs(self, room):
        """Create mob entities at mob_spawn tiles."""
        from server.game.entity import MobEntity
        from server.game.tile import TileType
        mob_count = 0
        for y, row in enumerate(room.tiles):
            for x, tile in enumerate(row):
                if tile.type == TileType.MOB_SPAWN:
                    mob_count += 1
                    mob = MobEntity(
                        id=f"mob_{room.room_key}_{mob_count}",
                        name=f"Slime #{mob_count}",
                        x=x, y=y,
                        entity_type="mob",
                        mob_type="slime",
                    )
                    room.add_entity(mob)

    def _register_handlers(self):
        from server.net.handlers.auth import handle_login, handle_register
        from server.net.handlers.movement import handle_move
        from server.net.handlers.chat import handle_chat
        from server.net.handlers.combat import handle_play_card, handle_pass_turn, handle_flee
        from server.net.handlers.inventory import handle_inventory

        game = self

        async def wrap(handler):
            async def inner(ws, data):
                await handler(ws, data, game=game)
            return inner

        # Use lambdas to bind game
        self.router.register("login", lambda ws, d: handle_login(ws, d, game=game))
        self.router.register("register", lambda ws, d: handle_register(ws, d, game=game))
        self.router.register("move", lambda ws, d: handle_move(ws, d, game=game))
        self.router.register("chat", lambda ws, d: handle_chat(ws, d, game=game))
        self.router.register("play_card", lambda ws, d: handle_play_card(ws, d, game=game))
        self.router.register("pass_turn", lambda ws, d: handle_pass_turn(ws, d, game=game))
        self.router.register("flee", lambda ws, d: handle_flee(ws, d, game=game))
        self.router.register("inventory", lambda ws, d: handle_inventory(ws, d, game=game))

    async def load_room(self, room_key: str):
        async with self.db_session() as session:
            from server.persistence.room_repo import RoomRepo
            repo = RoomRepo(session)
            room_row = await repo.get_by_key(room_key)
            if not room_row:
                return None
            room = self.room_manager.load_room(
                room_key=room_row.room_key,
                name=room_row.name,
                width=room_row.width,
                height=room_row.height,
                tile_data=room_row.tile_data,
                exits=room_row.exits or {},
                spawn_points=room_row.spawn_points or [],
            )
            self._spawn_room_mobs(room)
            return room

    async def save_player_position(self, entity_id: str):
        info = self.player_entities.get(entity_id)
        if not info:
            return
        async with self.db_session() as session:
            from server.persistence.player_repo import PlayerRepo
            repo = PlayerRepo(session)
            await repo.update_position(info["db_id"], info["room_key"], info["entity"].x, info["entity"].y)

    async def start_combat(self, player_entity_id: str, mob_entity_id: str, room_key: str):
        room = self.room_manager.get_room(room_key)
        if not room:
            return

        mob = room.entities.get(mob_entity_id)
        if not mob or not isinstance(mob, MobEntity) or not mob.is_alive:
            return

        player_info = self.player_entities.get(player_entity_id)
        if not player_info:
            return
        entity = player_info["entity"]

        # Create combat instance
        instance = self.combat_manager.create_instance(mob, self.card_defs)
        self.combat_manager.add_player_to_instance(instance.instance_id, entity)
        mob.is_alive = False  # Mark mob as in combat

        # Send combat start
        await self.connection_manager.send_to_player(
            player_entity_id,
            combat_start_message(
                instance.instance_id,
                [{"id": entity.id, "name": entity.name}],
                {"name": mob.name, "hp": instance.mob_hp},
            )
        )
        # Send first turn
        await self.connection_manager.send_to_player(
            player_entity_id,
            combat_turn_message(
                instance.instance_id,
                instance.current_player,
                instance.get_hand_for_player(player_entity_id),
                instance.mob_hp,
                instance.player_hps,
            )
        )

    async def broadcast_combat_state(self, instance):
        for pid in instance.participants:
            await self.connection_manager.send_to_player(
                pid,
                combat_turn_message(
                    instance.instance_id,
                    instance.current_player,
                    instance.get_hand_for_player(pid),
                    instance.mob_hp,
                    instance.player_hps,
                )
            )

    async def end_combat(self, instance):
        rewards = {}
        if instance.victory:
            rewards = {"xp": 25, "card_drop": instance.mob.loot_table[:1] if instance.mob.loot_table else []}

        for pid in instance.participants:
            info = self.player_entities.get(pid)
            if info:
                info["entity"].in_combat = False
            await self.connection_manager.send_to_player(
                pid, combat_end_message(instance.instance_id, instance.victory, rewards)
            )

        # Schedule mob respawn
        mob = instance.mob
        self.timer_service.schedule(
            f"respawn_{mob.id}",
            settings.MOB_RESPAWN_SECONDS,
            lambda: self._respawn_mob(mob),
        )

        self.combat_manager.remove_instance(instance.instance_id)

    async def _respawn_mob(self, mob: MobEntity):
        mob.is_alive = True
        mob.stats["hp"] = mob.stats.get("max_hp", 50)

    async def handle_disconnect(self, websocket: WebSocket):
        entity_id = self.connection_manager.disconnect(websocket)
        if entity_id:
            info = self.player_entities.pop(entity_id, None)
            if info:
                await self.save_player_position(entity_id)
                room = self.room_manager.get_room(info["room_key"])
                if room:
                    room.remove_entity(entity_id)
                    await self.connection_manager.broadcast_to_room(
                        room.get_player_ids(), entity_left_message(entity_id)
                    )

    def shutdown(self):
        self.timer_service.cancel_all()


# --- FastAPI App ---

game = Game()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await game.startup()
    yield
    game.shutdown()

app = FastAPI(title="The Ages", lifespan=lifespan)

@app.websocket("/ws/game")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(error_message("Invalid JSON"))
                continue
            await game.router.route(websocket, data)
    except WebSocketDisconnect:
        await game.handle_disconnect(websocket)
    except Exception:
        await game.handle_disconnect(websocket)

@app.get("/health")
async def health():
    return {"status": "ok"}

# Include web API routes
from server.web.routes_players import router as players_router
from server.web.routes_trades import router as trades_router
from server.web.routes_filters import router as filters_router
app.include_router(players_router, prefix="/api")
app.include_router(trades_router, prefix="/api")
app.include_router(filters_router, prefix="/api")
```

---

## Step 6b: Web API Endpoints

### File: `server/web/__init__.py`
Empty file.

### File: `server/web/auth.py`
```python
"""Shared web authentication utilities."""
from __future__ import annotations
import hashlib
import hmac
import json
import time
import base64
from server.config import settings

SECRET_KEY = "the-ages-secret-change-in-production"

def create_token(player_id: int, username: str) -> str:
    payload = {"player_id": player_id, "username": username, "exp": int(time.time()) + 86400}
    payload_bytes = json.dumps(payload).encode()
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode()
    sig = hmac.new(SECRET_KEY.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"

def verify_token(token: str) -> dict | None:
    try:
        payload_b64, sig = token.rsplit(".", 1)
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        expected_sig = hmac.new(SECRET_KEY.encode(), payload_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload = json.loads(payload_bytes)
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None
```

### File: `server/web/routes_players.py`
```python
"""Player profile and build viewing endpoints."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from server.models.base import async_session_factory
from server.persistence.player_repo import PlayerRepo

router = APIRouter(tags=["players"])

@router.get("/players/{player_id}/build")
async def get_player_build(player_id: int):
    async with async_session_factory() as session:
        repo = PlayerRepo(session)
        player = await repo.get_by_id(player_id)
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")
        return {
            "id": player.id,
            "username": player.username,
            "stats": player.stats,
            "level": (player.stats or {}).get("level", 1),
        }

@router.get("/players/{player_id}/cards")
async def get_player_cards(player_id: int):
    async with async_session_factory() as session:
        repo = PlayerRepo(session)
        player = await repo.get_by_id(player_id)
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")
        return {"id": player.id, "username": player.username, "cards": player.card_collection or []}
```

### File: `server/web/routes_trades.py`
```python
"""Card trading endpoints (in-memory for PoC)."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import uuid

router = APIRouter(tags=["trades"])

# In-memory trade storage for PoC
_trades: dict[str, dict] = {}

class TradeOffer(BaseModel):
    player_id: int
    offering_cards: list[str]
    requesting_cards: list[str]

@router.post("/trades/offer")
async def create_trade_offer(offer: TradeOffer):
    trade_id = str(uuid.uuid4())[:8]
    _trades[trade_id] = {
        "id": trade_id,
        "player_id": offer.player_id,
        "offering": offer.offering_cards,
        "requesting": offer.requesting_cards,
        "status": "open",
    }
    return _trades[trade_id]

@router.get("/trades")
async def list_trades():
    return [t for t in _trades.values() if t["status"] == "open"]

@router.post("/trades/{trade_id}/accept")
async def accept_trade(trade_id: str, accepter_id: int):
    trade = _trades.get(trade_id)
    if not trade or trade["status"] != "open":
        raise HTTPException(status_code=404, detail="Trade not found or not open")
    trade["status"] = "accepted"
    trade["accepted_by"] = accepter_id
    return trade
```

### File: `server/web/routes_filters.py`
```python
"""Custom filter CRUD endpoints (in-memory for PoC)."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import uuid

router = APIRouter(tags=["filters"])

_filters: dict[str, dict] = {}

class FilterCreate(BaseModel):
    player_id: int
    name: str
    criteria: dict  # flexible filter criteria

@router.get("/filters")
async def list_filters(player_id: int):
    return [f for f in _filters.values() if f["player_id"] == player_id]

@router.post("/filters")
async def create_filter(filter_data: FilterCreate):
    filter_id = str(uuid.uuid4())[:8]
    _filters[filter_id] = {
        "id": filter_id,
        "player_id": filter_data.player_id,
        "name": filter_data.name,
        "criteria": filter_data.criteria,
    }
    return _filters[filter_id]

@router.delete("/filters/{filter_id}")
async def delete_filter(filter_id: str):
    if filter_id not in _filters:
        raise HTTPException(status_code=404, detail="Filter not found")
    deleted = _filters.pop(filter_id)
    return {"deleted": True, "id": deleted["id"]}
```

---

## Step 7: Sample Data

### File: `data/rooms/town_square.json`
```json
{
  "name": "Town Square",
  "width": 12,
  "height": 10,
  "tiles": [
    ["wall","wall","wall","wall","wall","wall","wall","wall","wall","wall","wall","wall"],
    ["wall","floor","floor","floor","floor","floor","floor","floor","floor","floor","floor","wall"],
    ["wall","floor","floor","floor","floor","floor","floor","floor","floor","floor","floor","wall"],
    ["wall","floor","floor","floor","floor","floor","floor","floor","floor","floor","floor","wall"],
    ["wall","floor","floor","floor","floor","floor","floor","floor","floor","floor","floor","wall"],
    ["wall","floor","floor","floor","floor","floor","floor","floor","floor","floor","floor","wall"],
    ["wall","floor","floor","floor","floor","floor","floor","floor","floor","floor","floor","wall"],
    ["wall","floor","floor","floor","floor","floor","floor","floor","floor","floor","floor","wall"],
    ["wall","floor","floor","floor","floor","floor","floor","floor","floor","floor","floor","wall"],
    ["wall","wall","wall","wall","wall","exit","exit","wall","wall","wall","wall","wall"]
  ],
  "exits": {
    "south": {"x": 5, "y": 9, "target_room": "dark_cave", "entry_x": 5, "entry_y": 0},
    "south2": {"x": 6, "y": 9, "target_room": "dark_cave", "entry_x": 6, "entry_y": 0}
  },
  "spawn_points": [
    {"x": 5, "y": 5, "type": "player"},
    {"x": 6, "y": 5, "type": "player"}
  ]
}
```

### File: `data/rooms/dark_cave.json`
```json
{
  "name": "Dark Cave",
  "width": 10,
  "height": 12,
  "tiles": [
    ["wall","wall","wall","wall","wall","floor","floor","wall","wall","wall"],
    ["wall","floor","floor","floor","floor","floor","floor","floor","floor","wall"],
    ["wall","floor","floor","floor","floor","floor","floor","floor","floor","wall"],
    ["wall","floor","floor","wall","wall","floor","wall","wall","floor","wall"],
    ["wall","floor","floor","wall","floor","floor","floor","wall","floor","wall"],
    ["wall","floor","floor","floor","floor","mob_spawn","floor","floor","floor","wall"],
    ["wall","floor","floor","floor","floor","floor","floor","floor","floor","wall"],
    ["wall","floor","floor","wall","floor","floor","floor","wall","floor","wall"],
    ["wall","floor","floor","wall","wall","floor","wall","wall","floor","wall"],
    ["wall","floor","floor","floor","floor","mob_spawn","floor","floor","floor","wall"],
    ["wall","floor","floor","floor","floor","floor","floor","floor","floor","wall"],
    ["wall","wall","wall","wall","wall","wall","wall","wall","wall","wall"]
  ],
  "exits": {
    "north": {"x": 5, "y": 0, "target_room": "town_square", "entry_x": 5, "entry_y": 8},
    "north2": {"x": 6, "y": 0, "target_room": "town_square", "entry_x": 6, "entry_y": 8}
  },
  "spawn_points": [
    {"x": 5, "y": 1, "type": "player"}
  ]
}
```

### File: `data/cards/base_set.json`
```json
{
  "cards": [
    {"card_key": "slash", "name": "Slash", "cost": 1, "effect_type": "damage", "effect_value": 8, "description": "A quick slash with your blade."},
    {"card_key": "heavy_strike", "name": "Heavy Strike", "cost": 2, "effect_type": "damage", "effect_value": 15, "description": "A powerful overhead strike."},
    {"card_key": "fireball", "name": "Fireball", "cost": 3, "effect_type": "damage", "effect_value": 20, "description": "Hurl a ball of fire."},
    {"card_key": "quick_stab", "name": "Quick Stab", "cost": 1, "effect_type": "damage", "effect_value": 5, "description": "A fast but weak stab."},
    {"card_key": "heal", "name": "Heal", "cost": 2, "effect_type": "heal", "effect_value": 15, "description": "Restore health."},
    {"card_key": "minor_heal", "name": "Minor Heal", "cost": 1, "effect_type": "heal", "effect_value": 8, "description": "A small healing spell."},
    {"card_key": "shield_bash", "name": "Shield Bash", "cost": 2, "effect_type": "damage", "effect_value": 6, "description": "Bash with your shield, dealing damage."},
    {"card_key": "iron_guard", "name": "Iron Guard", "cost": 2, "effect_type": "shield", "effect_value": 12, "description": "Raise your guard, absorbing damage."},
    {"card_key": "wooden_shield", "name": "Wooden Shield", "cost": 1, "effect_type": "shield", "effect_value": 6, "description": "A basic defensive stance."},
    {"card_key": "poison_dart", "name": "Poison Dart", "cost": 1, "effect_type": "poison", "effect_value": 4, "description": "A poisoned dart."},
    {"card_key": "venom_strike", "name": "Venom Strike", "cost": 2, "effect_type": "poison", "effect_value": 10, "description": "A venomous attack."},
    {"card_key": "draw_cards", "name": "Tactical Insight", "cost": 1, "effect_type": "draw", "effect_value": 2, "description": "Draw 2 additional cards."},
    {"card_key": "double_slash", "name": "Double Slash", "cost": 2, "effect_type": "damage", "effect_value": 12, "description": "Two quick slashes in succession."},
    {"card_key": "full_heal", "name": "Full Heal", "cost": 3, "effect_type": "heal", "effect_value": 30, "description": "A powerful healing spell."},
    {"card_key": "fortify", "name": "Fortify", "cost": 3, "effect_type": "shield", "effect_value": 20, "description": "Greatly strengthen your defenses."}
  ]
}
```

---

## Step 8: Tests

### File: `tests/__init__.py`
Empty file.

### File: `tests/test_room.py`
```python
"""Tests for room, tile grid, and entity management."""
import pytest
from server.game.room import Room
from server.game.entity import PlayerEntity, MobEntity

def make_room():
    tiles = [
        ["wall", "wall", "wall", "wall", "wall"],
        ["wall", "floor", "floor", "floor", "wall"],
        ["wall", "floor", "floor", "floor", "wall"],
        ["wall", "floor", "floor", "floor", "wall"],
        ["wall", "wall", "wall", "exit", "wall"],
    ]
    exits = {"south": {"x": 3, "y": 4, "target_room": "other_room", "entry_x": 1, "entry_y": 0}}
    spawn_points = [{"x": 1, "y": 1, "type": "player"}]
    return Room("test_room", "Test Room", 5, 5, tiles, exits, spawn_points)

def make_player(x=1, y=1):
    return PlayerEntity(id="player_1", name="TestPlayer", x=x, y=y, entity_type="player")

class TestRoom:
    def test_create_room(self):
        room = make_room()
        assert room.room_key == "test_room"
        assert room.width == 5
        assert room.height == 5

    def test_add_entity(self):
        room = make_room()
        player = make_player()
        assert room.add_entity(player) is True
        assert "player_1" in room.entities

    def test_remove_entity(self):
        room = make_room()
        player = make_player()
        room.add_entity(player)
        removed = room.remove_entity("player_1")
        assert removed is player
        assert "player_1" not in room.entities

    def test_move_valid(self):
        room = make_room()
        player = make_player(x=1, y=1)
        room.add_entity(player)
        result = room.move_entity("player_1", "right")
        assert result["success"] is True
        assert result["x"] == 2
        assert result["y"] == 1

    def test_move_into_wall(self):
        room = make_room()
        player = make_player(x=1, y=1)
        room.add_entity(player)
        result = room.move_entity("player_1", "up")
        assert result["success"] is False

    def test_move_out_of_bounds(self):
        room = make_room()
        player = make_player(x=1, y=1)
        room.add_entity(player)
        result = room.move_entity("player_1", "left")
        # x=0 is a wall
        assert result["success"] is False

    def test_move_to_exit(self):
        room = make_room()
        player = make_player(x=3, y=3)
        room.add_entity(player)
        result = room.move_entity("player_1", "down")
        assert result["success"] is True
        assert result.get("exit") is True
        assert result["target_room"] == "other_room"

    def test_get_state(self):
        room = make_room()
        player = make_player()
        room.add_entity(player)
        state = room.get_state()
        assert state["room_key"] == "test_room"
        assert "player_1" in state["entities"]

    def test_get_entities_at(self):
        room = make_room()
        player = make_player(x=2, y=2)
        room.add_entity(player)
        entities = room.get_entities_at(2, 2)
        assert len(entities) == 1
        assert entities[0].id == "player_1"
```

### File: `tests/test_combat.py`
```python
"""Tests for combat instance and card resolution."""
import pytest
from server.game.combat_instance import CombatInstance
from server.game.entity import PlayerEntity, MobEntity
from server.game.card import CardDef, CardHand

def make_cards():
    return [
        CardDef("slash", "Slash", 1, "damage", 8, ""),
        CardDef("heal", "Heal", 2, "heal", 15, ""),
        CardDef("shield", "Shield", 1, "shield", 10, ""),
    ]

def make_mob():
    return MobEntity(id="mob_1", name="Slime", x=5, y=5, entity_type="mob", stats={"hp": 30, "max_hp": 30, "attack": 5, "defense": 2})

def make_player_entity():
    return PlayerEntity(id="player_1", name="Hero", x=1, y=1, entity_type="player", stats={"hp": 100, "max_hp": 100, "attack": 10, "defense": 5})

class TestCombat:
    def test_create_instance(self):
        mob = make_mob()
        instance = CombatInstance("test_combat", mob, make_cards())
        assert instance.instance_id == "test_combat"
        assert instance.mob_hp == 30

    def test_add_participant(self):
        mob = make_mob()
        instance = CombatInstance("test_combat", mob, make_cards())
        player = make_player_entity()
        instance.add_participant(player)
        assert len(instance.participants) == 1
        assert player.in_combat is True

    def test_play_card_damage(self):
        mob = make_mob()
        instance = CombatInstance("test_combat", mob, make_cards())
        player = make_player_entity()
        instance.add_participant(player)

        # Find a damage card in hand
        hand = instance.player_hands["player_1"]
        damage_cards = [c for c in hand.hand if c.effect_type == "damage"]
        if damage_cards:
            result = instance.play_card("player_1", damage_cards[0].card_key)
            assert result["success"] is True
            assert instance.mob_hp < 30

    def test_play_card_wrong_turn(self):
        mob = make_mob()
        instance = CombatInstance("test_combat", mob, make_cards())
        p1 = PlayerEntity(id="player_1", name="P1", x=0, y=0, entity_type="player")
        p2 = PlayerEntity(id="player_2", name="P2", x=0, y=0, entity_type="player")
        instance.add_participant(p1)
        instance.add_participant(p2)

        # Player 2 tries to play on player 1's turn
        hand = instance.player_hands["player_2"]
        if hand.hand:
            result = instance.play_card("player_2", hand.hand[0].card_key)
            assert result["success"] is False

    def test_pass_turn(self):
        mob = make_mob()
        instance = CombatInstance("test_combat", mob, make_cards())
        player = make_player_entity()
        instance.add_participant(player)

        initial_hp = instance.player_hps["player_1"]
        result = instance.pass_turn("player_1")
        assert result["success"] is True
        # Mob attacks when passing
        assert instance.player_hps["player_1"] <= initial_hp

    def test_victory(self):
        mob = MobEntity(id="mob_1", name="Weak Slime", x=5, y=5, entity_type="mob", stats={"hp": 1, "max_hp": 1, "attack": 1, "defense": 0})
        cards = [CardDef("slash", "Slash", 1, "damage", 50, "")]
        instance = CombatInstance("test_combat", mob, cards)
        player = make_player_entity()
        instance.add_participant(player)

        hand = instance.player_hands["player_1"]
        result = instance.play_card("player_1", hand.hand[0].card_key)
        assert instance.is_finished is True
        assert instance.victory is True

    def test_get_state(self):
        mob = make_mob()
        instance = CombatInstance("test_combat", mob, make_cards())
        player = make_player_entity()
        instance.add_participant(player)
        state = instance.get_state()
        assert "mob" in state
        assert "player_hps" in state
        assert state["current_player"] == "player_1"
```

### File: `tests/test_movement.py`
```python
"""Tests for movement edge cases and room transitions."""
import pytest
from server.game.room import Room
from server.game.room_manager import RoomManager
from server.game.entity import PlayerEntity, MobEntity

def make_two_rooms():
    room1_tiles = [
        ["wall", "wall", "wall", "wall", "wall"],
        ["wall", "floor", "floor", "floor", "wall"],
        ["wall", "floor", "floor", "floor", "wall"],
        ["wall", "floor", "floor", "floor", "wall"],
        ["wall", "wall", "wall", "exit", "wall"],
    ]
    room2_tiles = [
        ["wall", "wall", "wall", "floor", "wall"],
        ["wall", "floor", "floor", "floor", "wall"],
        ["wall", "floor", "floor", "floor", "wall"],
        ["wall", "floor", "floor", "floor", "wall"],
        ["wall", "wall", "wall", "wall", "wall"],
    ]
    room1_exits = {"south": {"x": 3, "y": 4, "target_room": "room2", "entry_x": 3, "entry_y": 0}}
    room2_exits = {"north": {"x": 3, "y": 0, "target_room": "room1", "entry_x": 3, "entry_y": 3}}

    manager = RoomManager()
    r1 = manager.load_room("room1", "Room 1", 5, 5, room1_tiles, room1_exits, [{"x": 1, "y": 1, "type": "player"}])
    r2 = manager.load_room("room2", "Room 2", 5, 5, room2_tiles, room2_exits, [{"x": 1, "y": 1, "type": "player"}])
    return manager, r1, r2

class TestMovement:
    def test_invalid_direction(self):
        _, room, _ = make_two_rooms()
        player = PlayerEntity(id="p1", name="P", x=1, y=1, entity_type="player")
        room.add_entity(player)
        result = room.move_entity("p1", "northwest")
        assert result["success"] is False

    def test_move_nonexistent_entity(self):
        _, room, _ = make_two_rooms()
        result = room.move_entity("ghost", "up")
        assert result["success"] is False

    def test_room_transfer(self):
        manager, room1, room2 = make_two_rooms()
        player = PlayerEntity(id="p1", name="P", x=3, y=3, entity_type="player")
        room1.add_entity(player)

        # Move to exit tile
        result = room1.move_entity("p1", "down")
        assert result.get("exit") is True

        # Transfer
        success = manager.transfer_entity(player, "room1", "room2", result["entry_x"], result["entry_y"])
        assert success is True
        assert "p1" not in room1.entities
        assert "p1" in room2.entities
        assert player.x == 3
        assert player.y == 0

    def test_mob_encounter(self):
        _, room, _ = make_two_rooms()
        mob = MobEntity(id="mob1", name="Slime", x=2, y=1, entity_type="mob")
        room.add_entity(mob)
        player = PlayerEntity(id="p1", name="P", x=1, y=1, entity_type="player")
        room.add_entity(player)
        result = room.move_entity("p1", "right")
        assert result["success"] is True
        assert result.get("mob_encounter") == "mob1"

    def test_sequential_moves(self):
        _, room, _ = make_two_rooms()
        player = PlayerEntity(id="p1", name="P", x=1, y=1, entity_type="player")
        room.add_entity(player)
        room.move_entity("p1", "right")
        room.move_entity("p1", "right")
        room.move_entity("p1", "down")
        assert player.x == 3
        assert player.y == 2

    def test_cant_walk_through_walls(self):
        _, room, _ = make_two_rooms()
        player = PlayerEntity(id="p1", name="P", x=1, y=1, entity_type="player")
        room.add_entity(player)
        # Try to walk into the top wall
        result = room.move_entity("p1", "up")
        assert result["success"] is False
```

### File: `tests/test_cards.py`
```python
"""Tests for card hand management."""
import pytest
from server.game.card import CardDef, CardHand

def make_deck():
    return [
        CardDef("slash", "Slash", 1, "damage", 8, ""),
        CardDef("heal", "Heal", 2, "heal", 15, ""),
        CardDef("shield", "Shield", 1, "shield", 10, ""),
        CardDef("fireball", "Fireball", 3, "damage", 20, ""),
        CardDef("stab", "Stab", 1, "damage", 5, ""),
        CardDef("potion", "Potion", 1, "heal", 8, ""),
        CardDef("block", "Block", 1, "shield", 6, ""),
    ]

class TestCardHand:
    def test_initial_draw(self):
        hand = CardHand(make_deck(), hand_size=5)
        assert len(hand.hand) == 5

    def test_play_card(self):
        hand = CardHand(make_deck(), hand_size=5)
        card_key = hand.hand[0].card_key
        played = hand.play(card_key)
        assert played is not None
        assert played.card_key == card_key
        # Should draw a replacement
        assert len(hand.hand) == 5

    def test_play_nonexistent_card(self):
        hand = CardHand(make_deck(), hand_size=5)
        played = hand.play("nonexistent")
        assert played is None

    def test_deck_reshuffles(self):
        deck = [CardDef("only", "Only", 1, "damage", 1, "")]
        hand = CardHand(deck, hand_size=1)
        assert len(hand.hand) == 1
        # Play it — goes to discard, deck is empty, should reshuffle
        hand.play("only")
        # After reshuffle, the card should be drawable again
        assert len(hand.hand) == 1

    def test_card_to_dict(self):
        card = CardDef("slash", "Slash", 1, "damage", 8, "A slash")
        d = card.to_dict()
        assert d["card_key"] == "slash"
        assert d["effect_value"] == 8
```

---

## All `__init__.py` files that need to be empty:
- `server/__init__.py`
- `server/models/__init__.py` (has content above)
- `server/game/__init__.py`
- `server/net/__init__.py`
- `server/net/handlers/__init__.py`
- `server/web/__init__.py`
- `server/persistence/__init__.py`
- `tests/__init__.py`

---

## Quick Start After Implementation

```bash
cd the-ages-server
pip install -e ".[dev]"
python run.py          # starts on port 8000
pytest tests/          # runs tests
curl localhost:8000/health  # should return {"status": "ok"}
```
