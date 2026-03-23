"""State helpers for interactive objects (player-scoped and room-scoped)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.room.models import PlayerObjectState, RoomState


# ---------------------------------------------------------------------------
# Player-scoped state (one state per player per object)
# ---------------------------------------------------------------------------

async def get_player_object_state(
    session: AsyncSession, player_id: int, room_key: str, object_id: str
) -> dict:
    """Read per-player state for an interactive object. Returns {} if none."""
    result = await session.execute(
        select(PlayerObjectState).where(
            PlayerObjectState.player_id == player_id,
            PlayerObjectState.room_key == room_key,
            PlayerObjectState.object_id == object_id,
        )
    )
    row = result.scalar_one_or_none()
    return row.state_data if row else {}


async def set_player_object_state(
    session: AsyncSession,
    player_id: int,
    room_key: str,
    object_id: str,
    state_data: dict,
) -> None:
    """Upsert per-player state for an interactive object."""
    result = await session.execute(
        select(PlayerObjectState).where(
            PlayerObjectState.player_id == player_id,
            PlayerObjectState.room_key == room_key,
            PlayerObjectState.object_id == object_id,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        row.state_data = state_data
    else:
        session.add(PlayerObjectState(
            player_id=player_id,
            room_key=room_key,
            object_id=object_id,
            state_data=state_data,
        ))
    await session.commit()


# ---------------------------------------------------------------------------
# Room-scoped state (shared across all players)
# ---------------------------------------------------------------------------

async def get_room_object_state(
    session: AsyncSession, room_key: str, object_id: str
) -> dict:
    """Read shared room state for an interactive object. Returns {} if none."""
    result = await session.execute(
        select(RoomState).where(RoomState.room_key == room_key)
    )
    room_state = result.scalar_one_or_none()
    if room_state is None:
        return {}
    return room_state.dynamic_state.get(object_id, {})


async def set_room_object_state(
    session: AsyncSession, room_key: str, object_id: str, state_data: dict
) -> None:
    """Upsert shared room state for an interactive object."""
    result = await session.execute(
        select(RoomState).where(RoomState.room_key == room_key)
    )
    room_state = result.scalar_one_or_none()
    if room_state is None:
        room_state = RoomState(room_key=room_key, mob_states={}, dynamic_state={})
        session.add(room_state)

    # Update the specific object's state within the JSON
    updated = dict(room_state.dynamic_state)
    updated[object_id] = state_data
    room_state.dynamic_state = updated
    await session.commit()
