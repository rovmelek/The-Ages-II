"""Player persistence repository."""
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

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
    await session.commit()
    await session.refresh(player)
    return player


async def save(session: AsyncSession, player: Player) -> Player:
    """Merge and commit a player instance."""
    merged = await session.merge(player)
    await session.commit()
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
    await session.commit()
