"""Player persistence repository."""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from server.core.constants import STAT_NAMES
from server.player.models import Player


async def get_by_username(session: AsyncSession, username: str) -> Player | None:
    """Find a player by username."""
    result = await session.execute(select(Player).where(Player.username == username))
    return result.scalar_one_or_none()


async def get_by_id(session: AsyncSession, player_id: int) -> Player | None:
    """Find a player by ID."""
    result = await session.execute(select(Player).where(Player.id == player_id))
    return result.scalar_one_or_none()


async def create(
    session: AsyncSession,
    username: str,
    password_hash: str,
    starting_room_id: str | None = None,
) -> Player:
    """Create a new player and return it."""
    player = Player(
        username=username,
        password_hash=password_hash,
        current_room_id=starting_room_id,
    )
    session.add(player)
    await session.flush()
    await session.refresh(player)
    return player


async def save(session: AsyncSession, player: Player) -> Player:
    """Merge and commit a player instance."""
    merged = await session.merge(player)
    return merged


async def update_position(
    session: AsyncSession,
    player_id: int,
    room_key: str,
    x: int,
    y: int,
) -> None:
    """Update a player's position and current room."""
    await session.execute(
        update(Player)
        .where(Player.id == player_id)
        .values(current_room_id=room_key, position_x=x, position_y=y)
    )


async def update_inventory(
    session: AsyncSession,
    player_id: int,
    inventory: dict,
) -> None:
    """Update a player's inventory JSON column."""
    await session.execute(
        update(Player)
        .where(Player.id == player_id)
        .values(inventory=inventory)
    )


async def update_visited_rooms(
    session: AsyncSession, player_id: int, visited_rooms: list
) -> None:
    """Update a player's visited rooms list."""
    await session.execute(
        update(Player).where(Player.id == player_id)
        .values(visited_rooms=visited_rooms)
    )


# attack excluded -- derived from STR/INT at runtime, not independently persisted.
# energy/max_energy included -- consumable resource like HP, must persist across sessions.
# shield/active_effects excluded -- combat-only transient.
_STATS_WHITELIST = {"hp", "max_hp", "energy", "max_energy", "xp", "level", *STAT_NAMES}


async def update_stats(
    session: AsyncSession,
    player_id: int,
    stats: dict,
) -> None:
    """Update a player's stats, stripping non-whitelisted keys."""
    filtered = {k: v for k, v in stats.items() if k in _STATS_WHITELIST}
    await session.execute(
        update(Player)
        .where(Player.id == player_id)
        .values(stats=filtered)
    )
