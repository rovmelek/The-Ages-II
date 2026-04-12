"""SpawnCheckpoint persistence repository."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.room.spawn_models import SpawnCheckpoint


async def get_checkpoint(
    session: AsyncSession, room_key: str, npc_key: str
) -> SpawnCheckpoint | None:
    """Find a spawn checkpoint by room key and NPC key."""
    result = await session.execute(
        select(SpawnCheckpoint).where(
            SpawnCheckpoint.npc_key == npc_key,
            SpawnCheckpoint.room_key == room_key,
        )
    )
    return result.scalar_one_or_none()


async def upsert_checkpoint(
    session: AsyncSession, room_key: str, npc_key: str, **kwargs
) -> SpawnCheckpoint:
    """Return existing checkpoint or create a new one.

    *kwargs* (e.g. next_check_at, currently_spawned) are applied only on
    creation.  An existing checkpoint is returned as-is for the caller to
    mutate.
    """
    existing = await get_checkpoint(session, room_key, npc_key)
    if existing is not None:
        return existing
    cp = SpawnCheckpoint(room_key=room_key, npc_key=npc_key, **kwargs)
    session.add(cp)
    await session.flush()
    return cp


async def get_all_checkpoints(session: AsyncSession) -> list[SpawnCheckpoint]:
    """Return every spawn checkpoint in the database."""
    result = await session.execute(select(SpawnCheckpoint))
    return list(result.scalars().all())
