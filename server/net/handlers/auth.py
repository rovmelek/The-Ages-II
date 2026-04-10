"""Authentication handlers for WebSocket clients."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import WebSocket

from server.core.database import async_session
from server.items import item_repo
from server.items.inventory import Inventory
from server.items.item_def import ItemDef
from server.player import repo as player_repo
from server.player.auth import hash_password, verify_password
from server.player.entity import PlayerEntity
from server.room import repo as room_repo

if TYPE_CHECKING:
    from server.app import Game

logger = logging.getLogger(__name__)


async def handle_register(websocket: WebSocket, data: dict, *, game: Game) -> None:
    """Handle the 'register' action: create a new player account."""
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if len(username) < 3:
        await websocket.send_json(
            {"type": "error", "detail": "Username must be at least 3 characters"}
        )
        return
    if len(password) < 6:
        await websocket.send_json(
            {"type": "error", "detail": "Password must be at least 6 characters"}
        )
        return

    async with async_session() as session:
        existing = await player_repo.get_by_username(session, username)
        if existing:
            await websocket.send_json(
                {"type": "error", "detail": "Username already taken"}
            )
            return

        hashed = hash_password(password)
        player = await player_repo.create(session, username, hashed)

        await websocket.send_json(
            {
                "type": "login_success",
                "player_id": player.id,
                "username": player.username,
            }
        )


async def _kick_old_session(entity_id: str, old_ws: WebSocket, game: Game) -> None:
    """Kick an existing session: save state, clean up, close old WebSocket."""
    # 1. Save old session state
    player_info = game.player_entities.get(entity_id)
    if player_info:
        entity = player_info["entity"]
        room_key = player_info["room_key"]
        inventory = player_info.get("inventory")

        try:
            async with async_session() as session:
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
        except Exception:
            pass  # Best-effort save

        # 2. Remove from combat
        combat_instance = game.combat_manager.get_player_instance(entity_id)
        if combat_instance:
            combat_instance.remove_participant(entity_id)
            game.combat_manager.remove_player(entity_id)
            if not combat_instance.participants:
                game.combat_manager.remove_instance(combat_instance.instance_id)
            else:
                state = combat_instance.get_state()
                for eid in combat_instance.participants:
                    ws = game.connection_manager.get_websocket(eid)
                    if ws:
                        await ws.send_json({"type": "combat_update", **state})

        # 3. Remove from room
        room = game.room_manager.get_room(room_key)
        if room:
            room.remove_entity(entity_id)
            await game.connection_manager.broadcast_to_room(
                room_key,
                {"type": "entity_left", "entity_id": entity_id},
                exclude=entity_id,
            )

    # 4. Remove from connection_manager and player_entities (before close)
    game.connection_manager.disconnect(entity_id)
    game.player_entities.pop(entity_id, None)

    # 5. Notify and close old WebSocket (best-effort)
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

    async with async_session() as session:
        player = await player_repo.get_by_username(session, username)
        if player is None or not verify_password(password, player.password_hash):
            await websocket.send_json(
                {"type": "error", "detail": "Invalid username or password"}
            )
            return

        # Create runtime entity from DB state
        entity_id = f"player_{player.id}"

        # Kick existing session if logged in from another connection
        old_ws = game.connection_manager.get_websocket(entity_id)
        if old_ws is not None:
            await _kick_old_session(entity_id, old_ws, game)

        # Resolve stats: apply defaults for first-time players, restore for returning
        _DEFAULT_STATS = {"hp": 100, "max_hp": 100, "attack": 10, "xp": 0}
        db_stats = player.stats or {}
        if not db_stats:
            # First-time player — apply defaults and persist
            stats = dict(_DEFAULT_STATS)
            await player_repo.update_stats(session, player.id, stats)
        else:
            # Returning player — use saved stats, fill any missing keys
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
        room_key = player.current_room_id or "town_square"

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
        game.connection_manager.connect(entity_id, websocket, room_key)

        # Restore inventory from DB (hydrate with item definitions)
        db_inventory = player.inventory or {}
        if db_inventory:
            all_items = await item_repo.get_all(session)
            item_defs = {i.item_key: ItemDef.from_db(i) for i in all_items}
            inventory = Inventory.from_dict(db_inventory, lambda k: item_defs.get(k))
        else:
            inventory = Inventory()

        # Track player entity with inventory
        game.player_entities[entity_id] = {
            "entity": entity,
            "room_key": room_key,
            "db_id": player.id,
            "inventory": inventory,
        }

        # Send login success and full room state
        await websocket.send_json(
            {
                "type": "login_success",
                "player_id": player.id,
                "username": player.username,
            }
        )
        await websocket.send_json({"type": "room_state", **room.get_state()})

        # Notify other players in the room
        entity_data = {
            "id": entity.id,
            "name": entity.name,
            "x": entity.x,
            "y": entity.y,
        }
        await game.connection_manager.broadcast_to_room(
            room_key,
            {"type": "entity_entered", "entity": entity_data},
            exclude=entity_id,
        )
