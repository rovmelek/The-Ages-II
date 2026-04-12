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
from server.player.entity import PlayerEntity
from server.room import repo as room_repo

if TYPE_CHECKING:
    from server.app import Game

logger = logging.getLogger(__name__)


async def _cleanup_trade(entity_id: str, game: Game) -> None:
    """Cancel any active trade for a disconnecting player."""
    cancelled_trade = game.trade_manager.cancel_trades_for(entity_id)
    if cancelled_trade:
        other_id = (
            cancelled_trade.player_b
            if cancelled_trade.player_a == entity_id
            else cancelled_trade.player_a
        )
        await game.connection_manager.send_to_player(
            other_id,
            {
                "type": "trade_result",
                "status": "cancelled",
                "reason": "Trade cancelled \u2014 player disconnected",
            },
        )


async def _cleanup_combat(entity_id: str, entity, game: Game) -> None:
    """Sync combat stats, remove from instance, notify remaining participants."""
    combat_instance = game.combat_manager.get_player_instance(entity_id)
    if not combat_instance:
        return

    # Sync combat stats back to entity (only whitelisted keys)
    combat_stats = combat_instance.participant_stats.get(entity_id, {})
    for key in ("hp", "max_hp"):
        if key in combat_stats:
            entity.stats[key] = combat_stats[key]
    # Restore HP if dead in combat
    if entity.stats.get("hp", 0) <= 0:
        entity.stats["hp"] = entity.stats.get("max_hp", settings.DEFAULT_BASE_HP)
    entity.in_combat = False

    # Remove from combat instance (destroys participant_stats entry)
    combat_instance.remove_participant(entity_id)
    game.combat_manager.remove_player(entity_id)

    if not combat_instance.participants:
        # Last player — release NPC and clean up instance
        if combat_instance.npc_id and combat_instance.room_key:
            room = game.room_manager.get_room(combat_instance.room_key)
            if room:
                npc = room.get_npc(combat_instance.npc_id)
                if npc:
                    npc.in_combat = False
        game.combat_manager.remove_instance(combat_instance.instance_id)
    else:
        # Notify remaining participants (best-effort per recipient)
        state = combat_instance.get_state()
        for eid in combat_instance.participants:
            ws = game.connection_manager.get_websocket(eid)
            if ws:
                try:
                    await ws.send_json({"type": "combat_update", **state})
                except Exception:
                    pass


async def _cleanup_party(entity_id: str, game: Game) -> None:
    """Remove from party, handle leader succession, clean up pending invites."""
    party_result, new_leader_id = game.party_manager.handle_disconnect(entity_id)
    if party_result and party_result.members:
        update_msg = {
            "type": "party_update",
            "action": "member_left",
            "entity_id": entity_id,
            "members": party_result.members,
            "leader": party_result.leader,
        }
        if new_leader_id:
            update_msg["new_leader"] = new_leader_id
        for mid in party_result.members:
            await game.connection_manager.send_to_player(mid, update_msg)

    from server.net.handlers.party import cleanup_pending_invites

    cleanup_pending_invites(entity_id)


async def _save_player_state(entity_id: str, player_info: dict, game: Game) -> None:
    """Persist player position, stats, inventory, and visited rooms to DB."""
    entity = player_info["entity"]
    room_key = player_info["room_key"]
    inventory = player_info.get("inventory")

    try:
        async with game.transaction() as session:
            await player_repo.update_position(
                session, entity.player_db_id, room_key, entity.x, entity.y
            )
            await player_repo.update_stats(
                session, entity.player_db_id, entity.stats
            )
            if inventory:
                await player_repo.update_inventory(
                    session, entity.player_db_id, inventory.to_dict()
                )
            visited_rooms = player_info.get("visited_rooms", [])
            if visited_rooms:
                await player_repo.update_visited_rooms(
                    session, entity.player_db_id, visited_rooms
                )
    except Exception:
        logger.exception("Failed to save state during cleanup for %s", entity_id)


async def _remove_from_room(entity_id: str, room_key: str, game: Game) -> None:
    """Remove entity from room and broadcast departure."""
    room = game.room_manager.get_room(room_key)
    if room:
        room.remove_entity(entity_id)
        await game.connection_manager.broadcast_to_room(
            room_key,
            {"type": "entity_left", "entity_id": entity_id},
            exclude=entity_id,
        )


async def _cleanup_player(entity_id: str, game: Game) -> None:
    """Clean up a player session: combat removal, state save, room removal.

    Used by both logout and same-socket re-login. Does NOT close the WebSocket
    or send any messages to the player.

    Cleanup order: trades → combat → party → save state → remove from room → disconnect
    """
    player_info = game.player_entities.get(entity_id)
    if not player_info:
        game.connection_manager.disconnect(entity_id)
        return

    entity = player_info["entity"]
    room_key = player_info["room_key"]

    await _cleanup_trade(entity_id, game)
    await _cleanup_combat(entity_id, entity, game)
    await _cleanup_party(entity_id, game)
    await _save_player_state(entity_id, player_info, game)
    await _remove_from_room(entity_id, room_key, game)

    game.connection_manager.disconnect(entity_id)
    game.player_entities.pop(entity_id, None)


async def handle_logout(websocket: WebSocket, data: dict, *, game: Game) -> None:
    """Handle the 'logout' action: save state, clean up, keep WebSocket open."""
    entity_id = game.connection_manager.get_entity_id(websocket)
    if entity_id is None:
        await websocket.send_json(
            {"type": "error", "detail": "Not logged in"}
        )
        return

    await _cleanup_player(entity_id, game)

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
                "username": player.username,
                "stats": {
                    "hp": default_max_hp,
                    "max_hp": default_max_hp,
                    "attack": settings.DEFAULT_ATTACK,
                    "xp": 0,
                    "level": 1,
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
    await _cleanup_player(entity_id, game)

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
                await _cleanup_player(entity_id, game)
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
        game.player_entities[entity_id] = {
            "entity": entity,
            "room_key": room_key,
            "db_id": player.id,
            "inventory": inventory,
            "visited_rooms": visited_rooms,
            "pending_level_ups": 0,
        }

        # Send login success and full room state
        await websocket.send_json(
            {
                "type": "login_success",
                "player_id": player.id,
                "username": player.username,
                "stats": {
                    "hp": stats.get("hp", settings.DEFAULT_BASE_HP),
                    "max_hp": stats.get("max_hp", settings.DEFAULT_BASE_HP),
                    "attack": stats.get("attack", settings.DEFAULT_ATTACK),
                    "xp": stats.get("xp", 0),
                    "level": stats.get("level", 1),
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
            game.player_entities[entity_id]["pending_level_ups"] = pending
            await send_level_up_available(entity_id, entity, game)
