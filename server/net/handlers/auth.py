"""Authentication handlers for WebSocket clients."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import WebSocket

from server.items import item_repo
from server.items.inventory import Inventory
from server.items.item_def import ItemDef
from server.player import repo as player_repo
from server.core.config import settings
from server.core.xp import get_pending_level_ups, send_level_up_available
from server.player.auth import hash_password, verify_password
from server.player.session import PlayerSession
from server.player.entity import PlayerEntity
from server.room import repo as room_repo

if TYPE_CHECKING:
    from server.app import Game

logger = logging.getLogger(__name__)


async def handle_logout(websocket: WebSocket, data: dict, *, game: Game) -> None:
    """Handle the 'logout' action: save state, clean up, keep WebSocket open."""
    entity_id = game.connection_manager.get_entity_id(websocket)
    if entity_id is None:
        await websocket.send_json(
            {"type": "error", "detail": "Not logged in"}
        )
        return

    await game.player_manager.cleanup_session(entity_id, game)

    # Send confirmation via raw websocket (connection_manager already cleared)
    try:
        await websocket.send_json({"type": "logged_out"})
    except Exception:
        pass  # Network dropped — cleanup already done


async def handle_register(websocket: WebSocket, data: dict, *, game: Game) -> None:
    """Handle the 'register' action: create a new player account."""
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if len(username) < settings.MIN_USERNAME_LENGTH:
        await websocket.send_json(
            {"type": "error", "detail": f"Username must be at least {settings.MIN_USERNAME_LENGTH} characters"}
        )
        return
    if len(password) < settings.MIN_PASSWORD_LENGTH:
        await websocket.send_json(
            {"type": "error", "detail": f"Password must be at least {settings.MIN_PASSWORD_LENGTH} characters"}
        )
        return

    async with game.transaction() as session:
        existing = await player_repo.get_by_username(session, username)
        if existing:
            await websocket.send_json(
                {"type": "error", "detail": "Username already taken"}
            )
            return

        hashed = hash_password(password)
        player = await player_repo.create(session, username, hashed)

        default_max_hp = settings.DEFAULT_BASE_HP + settings.DEFAULT_STAT_VALUE * settings.CON_HP_PER_POINT
        await websocket.send_json(
            {
                "type": "login_success",
                "player_id": player.id,
                "entity_id": f"player_{player.id}",
                "username": player.username,
                "stats": {
                    "hp": default_max_hp,
                    "max_hp": default_max_hp,
                    "attack": settings.DEFAULT_ATTACK,
                    "xp": 0,
                    "level": 1,
                    "xp_for_next_level": 1 * settings.XP_LEVEL_THRESHOLD_MULTIPLIER,
                    "xp_for_current_level": 0,
                    "strength": settings.DEFAULT_STAT_VALUE,
                    "dexterity": settings.DEFAULT_STAT_VALUE,
                    "constitution": settings.DEFAULT_STAT_VALUE,
                    "intelligence": settings.DEFAULT_STAT_VALUE,
                    "wisdom": settings.DEFAULT_STAT_VALUE,
                    "charisma": settings.DEFAULT_STAT_VALUE,
                },
            }
        )


async def _kick_old_session(entity_id: str, old_ws: WebSocket, game: Game) -> None:
    """Kick an existing session: save state, clean up, close old WebSocket."""
    await game.player_manager.cleanup_session(entity_id, game)

    # Notify and close old WebSocket (best-effort)
    try:
        await old_ws.send_json(
            {"type": "kicked", "reason": "Logged in from another location"}
        )
    except Exception:
        pass
    try:
        await old_ws.close(code=1000)
    except Exception:
        pass


async def handle_login(websocket: WebSocket, data: dict, *, game: Game) -> None:
    """Handle the 'login' action: authenticate and place player in room."""
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        await websocket.send_json(
            {"type": "error", "detail": "Username and password required"}
        )
        return

    async with game.transaction() as session:
        player = await player_repo.get_by_username(session, username)
        if player is None or not verify_password(password, player.password_hash):
            await websocket.send_json(
                {"type": "error", "detail": "Invalid username or password"}
            )
            return

        # Create runtime entity from DB state
        entity_id = f"player_{player.id}"

        # Handle existing session for this account
        old_ws = game.connection_manager.get_websocket(entity_id)
        if old_ws is not None:
            if old_ws is websocket:
                # Same socket re-login — inline cleanup without closing socket
                await game.player_manager.cleanup_session(entity_id, game)
            else:
                # Different socket — kick the old session
                await _kick_old_session(entity_id, old_ws, game)

        # Resolve stats: apply defaults for first-time players, restore for returning
        _DEFAULT_STATS = {
            "hp": settings.DEFAULT_BASE_HP, "max_hp": settings.DEFAULT_BASE_HP,
            "attack": settings.DEFAULT_ATTACK, "xp": 0, "level": 1,
            "strength": settings.DEFAULT_STAT_VALUE, "dexterity": settings.DEFAULT_STAT_VALUE,
            "constitution": settings.DEFAULT_STAT_VALUE, "intelligence": settings.DEFAULT_STAT_VALUE,
            "wisdom": settings.DEFAULT_STAT_VALUE, "charisma": settings.DEFAULT_STAT_VALUE,
        }
        db_stats = player.stats or {}
        if not db_stats:
            # First-time player — apply defaults, compute max_hp from CON
            stats = dict(_DEFAULT_STATS)
            stats["max_hp"] = settings.DEFAULT_BASE_HP + stats["constitution"] * settings.CON_HP_PER_POINT
            stats["hp"] = stats["max_hp"]
            await player_repo.update_stats(session, player.id, stats)
        else:
            # Returning player — use saved stats, fill any missing keys
            # max_hp is NOT recalculated from CON (preserves existing state)
            stats = {**_DEFAULT_STATS, **db_stats}

        entity = PlayerEntity(
            id=entity_id,
            name=player.username,
            x=player.position_x,
            y=player.position_y,
            player_db_id=player.id,
            stats=stats,
        )

        # Determine room (default to town_square for first login)
        room_key = player.current_room_id or settings.DEFAULT_SPAWN_ROOM

        # Load room if not already in memory
        room = game.room_manager.get_room(room_key)
        if room is None:
            room_db = await room_repo.get_by_key(session, room_key)
            if room_db is None:
                await websocket.send_json(
                    {"type": "error", "detail": "Room not found"}
                )
                return
            room = game.room_manager.load_room(room_db)

        # Place player at a safe position
        is_first_login = player.current_room_id is None
        needs_relocation = is_first_login or not room.is_walkable(entity.x, entity.y)
        if needs_relocation:
            sx, sy = room.get_player_spawn()
            if not room.is_walkable(sx, sy):
                sx, sy = room.find_first_walkable()
            if not room.is_walkable(sx, sy):
                logger.warning(
                    "Room %s has no walkable tile; placing %s at (%d, %d)",
                    room_key, entity.name, sx, sy,
                )
            entity.x = sx
            entity.y = sy
            await player_repo.update_position(session, player.id, room_key, sx, sy)

        # Place entity in room and register WebSocket connection
        room.add_entity(entity)
        game.connection_manager.connect(entity_id, websocket, room_key, name=player.username)

        # Restore inventory from DB (hydrate with item definitions)
        db_inventory = player.inventory or {}
        if db_inventory:
            all_items = await item_repo.get_all(session)
            item_defs = {i.item_key: ItemDef.from_db(i) for i in all_items}
            inventory = Inventory.from_dict(db_inventory, lambda k: item_defs.get(k))
        else:
            inventory = Inventory()

        # Restore visited rooms from DB; ensure current room is tracked
        visited_rooms = player.visited_rooms or []
        if room_key not in visited_rooms:
            visited_rooms.append(room_key)

        # Track player entity with inventory and visited rooms
        game.player_manager.set_session(entity_id, PlayerSession(
            entity=entity,
            room_key=room_key,
            db_id=player.id,
            inventory=inventory,
            visited_rooms=set(visited_rooms),
            pending_level_ups=0,
        ))

        # Send login success and full room state
        await websocket.send_json(
            {
                "type": "login_success",
                "player_id": player.id,
                "entity_id": entity_id,
                "username": player.username,
                "stats": {
                    "hp": stats.get("hp", settings.DEFAULT_BASE_HP),
                    "max_hp": stats.get("max_hp", settings.DEFAULT_BASE_HP),
                    "attack": stats.get("attack", settings.DEFAULT_ATTACK),
                    "xp": stats.get("xp", 0),
                    "level": stats.get("level", 1),
                    "xp_for_next_level": stats.get("level", 1) * settings.XP_LEVEL_THRESHOLD_MULTIPLIER,
                    "xp_for_current_level": (stats.get("level", 1) - 1) * settings.XP_LEVEL_THRESHOLD_MULTIPLIER,
                    "strength": stats.get("strength", settings.DEFAULT_STAT_VALUE),
                    "dexterity": stats.get("dexterity", settings.DEFAULT_STAT_VALUE),
                    "constitution": stats.get("constitution", settings.DEFAULT_STAT_VALUE),
                    "intelligence": stats.get("intelligence", settings.DEFAULT_STAT_VALUE),
                    "wisdom": stats.get("wisdom", settings.DEFAULT_STAT_VALUE),
                    "charisma": stats.get("charisma", settings.DEFAULT_STAT_VALUE),
                },
            }
        )
        await websocket.send_json({"type": "room_state", **room.get_state()})

        # Notify other players in the room
        entity_data = {
            "id": entity.id,
            "name": entity.name,
            "x": entity.x,
            "y": entity.y,
            "level": stats.get("level", 1),
        }
        await game.connection_manager.broadcast_to_room(
            room_key,
            {"type": "entity_entered", "entity": entity_data},
            exclude=entity_id,
        )

        # Re-check for pending level-ups (e.g., player disconnected before choosing)
        pending = get_pending_level_ups(stats)
        if pending > 0:
            session = game.player_manager.get_session(entity_id)
            if session:
                session.pending_level_ups = pending
            await send_level_up_available(entity_id, entity, game)
