"""Room persistence repository."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.room.models import Room, RoomState


async def get_by_key(session: AsyncSession, room_key: str) -> Room | None:
    """Find a room by its unique key."""
    result = await session.execute(select(Room).where(Room.room_key == room_key))
    return result.scalar_one_or_none()


async def get_state(session: AsyncSession, room_key: str) -> RoomState | None:
    """Get the runtime state for a room."""
    result = await session.execute(select(RoomState).where(RoomState.room_key == room_key))
    return result.scalar_one_or_none()


async def save_state(session: AsyncSession, room_state: RoomState) -> RoomState:
    """Merge and commit a room state."""
    merged = await session.merge(room_state)
    await session.flush()
    return merged


async def upsert_room(session: AsyncSession, room: Room) -> Room:
    """Insert or update a room by room_key."""
    existing = await get_by_key(session, room.room_key)
    if existing:
        existing.name = room.name
        existing.schema_version = room.schema_version
        existing.width = room.width
        existing.height = room.height
        existing.tile_data = room.tile_data
        existing.exits = room.exits
        existing.objects = room.objects
        existing.spawn_points = room.spawn_points
        return existing
    session.add(room)
    await session.flush()
    await session.refresh(room)
    return room
