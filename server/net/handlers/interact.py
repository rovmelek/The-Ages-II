"""Interact handler for WebSocket clients."""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import WebSocket

import server.room.objects  # noqa: F401 — triggers type registration
from server.room.objects.base import InteractiveObject
from server.room.objects.registry import create_object

if TYPE_CHECKING:
    from server.app import Game


async def handle_interact(websocket: WebSocket, data: dict, *, game: Game) -> None:
    """Handle the 'interact' action: delegate to object-specific handler."""
    entity_id = game.connection_manager.get_entity_id(websocket)
    if entity_id is None:
        await websocket.send_json({"type": "error", "detail": "Not logged in"})
        return

    player_info = game.player_entities.get(entity_id)
    if player_info is None:
        await websocket.send_json({"type": "error", "detail": "Not logged in"})
        return

    room_key = player_info["room_key"]
    player_db_id = player_info["db_id"]

    target_id = data.get("target_id", "")
    if not target_id:
        await websocket.send_json({"type": "error", "detail": "Missing target_id"})
        return

    # Find the object in the room
    room = game.room_manager.get_room(room_key)
    if room is None:
        await websocket.send_json({"type": "error", "detail": "Room not found"})
        return

    obj_dict = room.get_object(target_id)
    if obj_dict is None:
        await websocket.send_json({"type": "error", "detail": "Object not found"})
        return

    # Adjacency check — player must be within Manhattan distance 1
    entity = player_info["entity"]
    obj_x, obj_y = obj_dict["x"], obj_dict["y"]
    if abs(entity.x - obj_x) + abs(entity.y - obj_y) > 1:
        await websocket.send_json({"type": "error", "detail": "Too far to interact"})
        return

    # Build the typed object and check if it's interactive
    obj = create_object(obj_dict)
    if not isinstance(obj, InteractiveObject):
        await websocket.send_json({"type": "error", "detail": "Object not interactable"})
        return

    # Delegate to the object's interact method
    result = await obj.interact(player_db_id, game)
    await websocket.send_json({
        "type": "interact_result",
        "object_id": target_id,
        "result": result,
    })
