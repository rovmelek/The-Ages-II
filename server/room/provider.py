"""Room provider interface and JSON implementation."""
import json
from abc import ABC, abstractmethod
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from server.core.config import settings
from server.room.models import Room
from server.room import repo as room_repo


class RoomProvider(ABC):
    """Abstract interface for loading room definitions into the database."""

    @abstractmethod
    async def load_rooms(self, session: AsyncSession) -> list[Room]:
        """Load room definitions and persist them to the database."""
        ...


class JsonRoomProvider(RoomProvider):
    """Loads room definitions from JSON files in data/rooms/."""

    def __init__(self, rooms_dir: Path | None = None):
        self.rooms_dir = rooms_dir or (settings.DATA_DIR / "rooms")

    async def load_rooms(self, session: AsyncSession) -> list[Room]:
        """Read all .json files from rooms directory and upsert into database."""
        rooms: list[Room] = []
        if not self.rooms_dir.exists():
            return rooms

        for json_file in sorted(self.rooms_dir.glob("*.json")):
            with open(json_file) as f:
                data = json.load(f)
            room = Room(
                room_key=data["room_key"],
                name=data["name"],
                schema_version=data.get("schema_version", 1),
                width=data["width"],
                height=data["height"],
                tile_data=data.get("tile_data", []),
                exits=data.get("exits", []),
                objects=data.get("objects", []),
                spawn_points=data.get("spawn_points", []),
            )
            persisted = await room_repo.upsert_room(session, room)
            rooms.append(persisted)

        return rooms
