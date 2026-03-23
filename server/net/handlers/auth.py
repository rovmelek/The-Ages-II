"""Authentication handlers for WebSocket clients."""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import WebSocket

from server.core.database import async_session
from server.items.inventory import Inventory
from server.player import repo as player_repo
from server.player.auth import hash_password, verify_password
from server.player.entity import PlayerEntity
from server.room import repo as room_repo

if TYPE_CHECKING:
    from server.app import Game


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
        entity = PlayerEntity(
            id=entity_id,
            name=player.username,
            x=player.position_x,
            y=player.position_y,
            player_db_id=player.id,
            stats=player.stats or {},
        )

        # Determine room (default to test_room for first login)
        room_key = player.current_room_id or "test_room"

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

        # Place entity in room and register WebSocket connection
        room.add_entity(entity)
        game.connection_manager.connect(entity_id, websocket, room_key)

        # Track player entity with inventory
        game.player_entities[entity_id] = {
            "entity": entity,
            "room_key": room_key,
            "db_id": player.id,
            "inventory": Inventory(),
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
