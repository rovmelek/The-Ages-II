"""Player session setup service — shared helpers for login and reconnect."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import WebSocket

from server.core.config import settings
from server.core.constants import PROTOCOL_VERSION, SPAWN_PERSISTENT, STAT_NAMES
from server.core.xp import get_pending_level_ups
from server.net.xp_notifications import send_level_up_available
from server.items import item_repo
from server.items.inventory import Inventory
from server.items.item_def import ItemDef
from server.net.schemas import with_request_id
from server.player import repo as player_repo
from server.player.entity import PlayerEntity
from server.player.session import PlayerSession
from server.room import repo as room_repo

if TYPE_CHECKING:
    from server.app import Game

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers — moved from auth.py
# ---------------------------------------------------------------------------


def _default_stats() -> dict[str, int]:
    """Build default stats from current settings.

    Function (not constant) to support test monkeypatching — reads settings.*
    on each call so patched values are always reflected (ADR-16-7).
    """
    result = {
        "hp": settings.DEFAULT_BASE_HP, "max_hp": settings.DEFAULT_BASE_HP,
        "attack": settings.DEFAULT_ATTACK, "xp": 0, "level": 1,
    }
    for s in STAT_NAMES:
        result[s] = settings.DEFAULT_STAT_VALUE
    return result


async def _resolve_stats(player, session) -> dict:
    """Resolve player stats: apply defaults for first-time, restore for returning."""
    db_stats = player.stats or {}
    if not db_stats:
        stats = _default_stats()
        stats["max_hp"] = settings.DEFAULT_BASE_HP + stats["constitution"] * settings.CON_HP_PER_POINT
        stats["hp"] = stats["max_hp"]
        await player_repo.update_stats(session, player.id, stats)
    else:
        stats = {**_default_stats(), **db_stats}
    return stats


def find_spawn_point(room, room_key: str, entity_name: str) -> tuple[int, int]:
    """Find a walkable spawn point in the given room.

    Public function — used by both _resolve_room_and_place and Game.respawn_player.
    """
    sx, sy = room.get_player_spawn()
    if not room.is_walkable(sx, sy):
        sx, sy = room.find_first_walkable()
    if not room.is_walkable(sx, sy):
        logger.warning(
            "Room %s has no walkable tile; placing %s at (%d, %d)",
            room_key, entity_name, sx, sy,
        )
    return sx, sy


async def _resolve_room_and_place(entity, player, room_key: str, game: Game, session):
    """Load room if needed, find safe spawn position, update DB if relocated.

    Raises ValueError if the room cannot be found.
    """
    room = game.room_manager.get_room(room_key)
    if room is None:
        room_db = await room_repo.get_by_key(session, room_key)
        if room_db is None:
            raise ValueError("Room not found")
        room = game.room_manager.load_room(room_db)

    is_first_login = player.current_room_id is None
    needs_relocation = is_first_login or not room.is_walkable(entity.x, entity.y)
    if needs_relocation:
        sx, sy = find_spawn_point(room, room_key, entity.name)
        entity.x = sx
        entity.y = sy
        await player_repo.update_position(session, player.id, room_key, sx, sy)
    return room_key, room


async def _hydrate_inventory(player, session) -> Inventory:
    """Rebuild runtime Inventory from DB state."""
    db_inventory = player.inventory or {}
    if db_inventory:
        all_items = await item_repo.get_all(session)
        item_defs = {i.item_key: ItemDef.from_db(i) for i in all_items}
        return Inventory.from_dict(db_inventory, lambda k: item_defs.get(k))
    return Inventory()


# ---------------------------------------------------------------------------
# Stats payload
# ---------------------------------------------------------------------------


def build_stats_payload(stats: dict) -> dict:
    """Build the canonical stats payload dict from a stats dict.

    Used by _build_login_response, handle_register, and handle_stats.
    """
    level = stats.get("level", 1)
    return {
        "hp": stats.get("hp", settings.DEFAULT_BASE_HP),
        "max_hp": stats.get("max_hp", settings.DEFAULT_BASE_HP),
        "attack": stats.get("attack", settings.DEFAULT_ATTACK),
        "xp": stats.get("xp", 0),
        "level": level,
        "xp_for_next_level": level * settings.XP_LEVEL_THRESHOLD_MULTIPLIER,
        "xp_for_current_level": (level - 1) * settings.XP_LEVEL_THRESHOLD_MULTIPLIER,
        **{s: stats.get(s, settings.DEFAULT_STAT_VALUE) for s in STAT_NAMES},
    }


def _build_login_response(
    db_id: int, entity_id: str, username: str, stats: dict,
    session_token: str | None = None,
) -> dict:
    """Construct the login_success JSON payload."""
    result = {
        "type": "login_success",
        "protocol_version": PROTOCOL_VERSION,
        "player_id": db_id,
        "entity_id": entity_id,
        "username": username,
        "stats": build_stats_payload(stats),
    }
    if session_token is not None:
        result["session_token"] = session_token
    return result


# ---------------------------------------------------------------------------
# Full session setup — shared between login and reconnect Case 2
# ---------------------------------------------------------------------------


async def setup_full_session(
    *,
    websocket: WebSocket,
    player,
    session,
    game: Game,
    session_token: str,
    data: dict,
) -> bool:
    """Set up a full player session (login or reconnect Case 2).

    Returns True on success, False if room not found (error already sent).
    The caller owns the transaction and passes the DB player row + session.
    """
    stats = await _resolve_stats(player, session)
    entity_id = f"player_{player.id}"
    entity = PlayerEntity(
        id=entity_id, name=player.username,
        x=player.position_x, y=player.position_y,
        player_db_id=player.id, stats=stats,
    )
    room_key = player.current_room_id or settings.DEFAULT_SPAWN_ROOM
    try:
        room_key, room = await _resolve_room_and_place(entity, player, room_key, game, session)
    except ValueError:
        await websocket.send_json(with_request_id({"type": "error", "detail": "Room not found"}, data))
        return False

    room.add_entity(entity)
    game.connection_manager.connect(entity_id, websocket, room_key, name=player.username)
    inventory = await _hydrate_inventory(player, session)
    visited_rooms = player.visited_rooms or []
    if room_key not in visited_rooms:
        visited_rooms.append(room_key)
    game.player_manager.set_session(entity_id, PlayerSession(
        entity=entity, room_key=room_key, db_id=player.id,
        inventory=inventory, visited_rooms=set(visited_rooms), pending_level_ups=0,
    ))
    await websocket.send_json(with_request_id(
        _build_login_response(player.id, entity_id, player.username, stats, session_token=session_token),
        data,
    ))
    await websocket.send_json({"type": "room_state", **room.get_state()})
    await game.connection_manager.broadcast_to_room(
        room_key,
        {"type": "entity_entered", "entity": {
            "id": entity.id, "name": entity.name,
            "x": entity.x, "y": entity.y, "level": stats.get("level", 1),
        }},
        exclude=entity_id,
    )
    pending = get_pending_level_ups(stats)
    if pending > 0:
        player_session = game.player_manager.get_session(entity_id)
        if player_session:
            player_session.pending_level_ups = pending
        await send_level_up_available(entity_id, entity, game)
    game._start_heartbeat(entity_id)
    return True


# ---------------------------------------------------------------------------
# NPC and respawn — moved from Game class (Story 17.8)
# ---------------------------------------------------------------------------


async def kill_npc(game: Game, room_key: str, npc_id: str) -> None:
    """Mark an NPC as dead and schedule respawn if persistent."""
    room = game.room_manager.get_room(room_key)
    if room is None:
        return
    npc = room.get_npc(npc_id)
    if npc is None or not npc.is_alive:
        return

    npc.is_alive = False
    npc.in_combat = False

    # Schedule respawn for persistent NPCs
    tmpl = game.npc_templates.get(npc.npc_key)
    if tmpl and tmpl.get("spawn_type") == SPAWN_PERSISTENT:
        respawn_seconds = tmpl.get("spawn_config", {}).get("respawn_seconds", settings.MOB_RESPAWN_SECONDS)
        game.scheduler.schedule_respawn(room_key, npc_id, respawn_seconds)


def _reset_player_stats(entity) -> None:
    """Clear combat flags and restore HP to max for respawn."""
    entity.in_combat = False
    entity.stats["hp"] = entity.stats.get("max_hp", settings.DEFAULT_BASE_HP)
    entity.stats.pop("shield", None)


async def respawn_player(game: Game, entity_id: str) -> None:
    """Respawn a defeated player in town_square with full HP."""
    player_info = game.player_manager.get_session(entity_id)
    if player_info is None:
        return

    entity = player_info.entity
    old_room_key = player_info.room_key

    _reset_player_stats(entity)

    spawn_room_key = settings.DEFAULT_SPAWN_ROOM
    spawn_room = game.room_manager.get_room(spawn_room_key)
    if spawn_room is None:
        return  # Cannot respawn without town_square

    sx, sy = find_spawn_point(spawn_room, spawn_room_key, entity.name)

    # Save to DB FIRST (crash recovery: player placed correctly on re-login)
    try:
        async with game.transaction() as session:
            await player_repo.update_position(
                session, entity.player_db_id, spawn_room_key, sx, sy
            )
            await player_repo.update_stats(
                session, entity.player_db_id, entity.stats
            )
    except Exception:
        pass  # Best-effort DB save

    # In-memory room transfer
    old_room = game.room_manager.get_room(old_room_key)
    if old_room and old_room_key != spawn_room_key:
        old_room.remove_entity(entity_id)
        await game.connection_manager.broadcast_to_room(
            old_room_key,
            {"type": "entity_left", "entity_id": entity_id},
            exclude=entity_id,
        )

    entity.x = sx
    entity.y = sy
    spawn_room.add_entity(entity)
    player_info.room_key = spawn_room_key
    game.connection_manager.update_room(entity_id, spawn_room_key)

    # Send respawn + new room state to player
    ws = game.connection_manager.get_websocket(entity_id)
    if ws:
        await ws.send_json({
            "type": "respawn",
            "room_key": spawn_room_key,
            "x": sx,
            "y": sy,
            "hp": entity.stats["hp"],
            "max_hp": entity.stats["max_hp"],
        })
        await ws.send_json({"type": "room_state", **spawn_room.get_state()})

    # Notify town_square players
    await game.connection_manager.broadcast_to_room(
        spawn_room_key,
        {
            "type": "entity_entered",
            "entity": {"id": entity.id, "name": entity.name, "x": sx, "y": sy},
        },
        exclude=entity_id,
    )
