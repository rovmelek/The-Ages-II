"""Interact handler for WebSocket clients."""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import WebSocket

from server.core.config import settings
from server.core.xp import grant_xp
import server.room.objects  # noqa: F401 — triggers type registration
from server.room.objects.base import InteractiveObject
from server.room.objects.registry import create_object
from server.room.objects.state import get_player_object_state, set_player_object_state
from server.room.room import DIRECTION_DELTAS

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
    entity = player_info["entity"]

    # Get room
    room = game.room_manager.get_room(room_key)
    if room is None:
        await websocket.send_json({"type": "error", "detail": "Room not found"})
        return

    # Resolve target object from either target_id or direction
    target_id = data.get("target_id", "")
    direction = data.get("direction", "")

    if target_id:
        # Existing path: lookup by ID
        obj_dict = room.get_object(target_id)
        if obj_dict is None:
            await websocket.send_json({"type": "error", "detail": "Object not found"})
            return

        # Adjacency check — player must be within Manhattan distance 1
        obj_x, obj_y = obj_dict["x"], obj_dict["y"]
        if abs(entity.x - obj_x) + abs(entity.y - obj_y) > 1:
            await websocket.send_json({"type": "error", "detail": "Too far to interact"})
            return

    elif direction:
        # New path: resolve from direction
        if direction not in DIRECTION_DELTAS:
            await websocket.send_json(
                {"type": "error", "detail": f"Invalid direction: {direction}"}
            )
            return

        dx, dy = DIRECTION_DELTAS[direction]
        tx, ty = entity.x + dx, entity.y + dy

        if tx < 0 or ty < 0 or tx >= room.width or ty >= room.height:
            await websocket.send_json(
                {"type": "error", "detail": "Nothing to interact with in that direction"}
            )
            return

        # Search interactive objects at (tx, ty)
        obj_dict = None
        for obj in room._interactive_objects.values():
            if obj["x"] == tx and obj["y"] == ty:
                obj_dict = obj
                break

        if obj_dict is None:
            await websocket.send_json(
                {"type": "error", "detail": "Nothing to interact with in that direction"}
            )
            return

        target_id = obj_dict["id"]
        # No adjacency check needed — direction guarantees distance 1

    else:
        await websocket.send_json(
            {"type": "error", "detail": "Missing target_id or direction"}
        )
        return

    # Build the typed object and check if it's interactive
    obj = create_object(obj_dict)
    if not isinstance(obj, InteractiveObject):
        await websocket.send_json({"type": "error", "detail": "Object not interactable"})
        return

    # Check if this is first interaction (before interact modifies state)
    first_interaction = False
    async with game.transaction() as session:
        prior_state = await get_player_object_state(
            session, player_db_id, room_key, target_id,
        )
        if not prior_state:
            first_interaction = True

    # Delegate to the object's interact method
    result = await obj.interact(player_db_id, game)

    # Grant interaction XP on first successful interaction
    if first_interaction and result.get("status") not in ("error", "already_looted"):
        await grant_xp(
            entity_id, entity, settings.XP_INTERACTION_REWARD,
            "interaction", f"Interacted with {obj_dict.get('type', 'object')}", game,
        )
        # For levers (room-scoped state), record per-player interaction for XP tracking
        if obj_dict.get("type") == "lever":
            async with game.transaction() as session:
                await set_player_object_state(
                    session, player_db_id, room_key, target_id, {"interacted": True},
                )

    await websocket.send_json({
        "type": "interact_result",
        "object_id": target_id,
        "result": result,
    })
