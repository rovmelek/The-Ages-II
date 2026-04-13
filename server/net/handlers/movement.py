"""Movement handler for WebSocket clients."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import WebSocket

from server.core.config import settings
from server.net.xp_notifications import grant_xp
from server.net.auth_middleware import requires_auth
from server.net.schemas import with_request_id
from server.player import repo as player_repo
from server.player.service import find_spawn_point
from server.player.session import PlayerSession
from server.room import repo as room_repo
from server.room.room import DIRECTION_DELTAS

if TYPE_CHECKING:
    from server.app import Game

logger = logging.getLogger(__name__)


def _find_nearby_objects(room, x: int, y: int) -> list[dict]:
    """Scan 4 adjacent tiles for interactive objects."""
    nearby = []
    for direction, (dx, dy) in DIRECTION_DELTAS.items():
        tx, ty = x + dx, y + dy
        if tx < 0 or ty < 0 or tx >= room.width or ty >= room.height:
            continue
        for obj in room.interactive_objects.values():
            if obj.x == tx and obj.y == ty:
                nearby.append({"id": obj.id, "type": obj.type, "direction": direction})
    return nearby


@requires_auth
async def handle_move(
    websocket: WebSocket, data: dict, *, game: Game,
    entity_id: str, player_info: PlayerSession,
) -> None:
    """Handle the 'move' action: move player in a direction on the tile grid."""
    entity = player_info.entity
    room_key = player_info.room_key

    # Cannot move while in combat
    if entity.in_combat:
        await websocket.send_json(
            with_request_id({"type": "error", "detail": "Cannot move while in combat"}, data)
        )
        return

    direction = data.get("direction", "")

    room = game.room_manager.get_room(room_key)
    if room is None:
        await websocket.send_json(with_request_id({"type": "error", "detail": "Room not found"}, data))
        return

    # Save old position for revert on failed exit transition
    old_x, old_y = entity.x, entity.y

    result = room.move_entity(entity_id, direction)

    if not result["success"]:
        reason = result["reason"]
        if reason == "invalid_direction":
            detail = f"Invalid direction: {direction}"
        elif reason == "wall":
            detail = "Tile not walkable"
        elif reason == "bounds":
            detail = "Out of bounds"
        else:
            detail = "Move failed"
        await websocket.send_json(with_request_id({"type": "error", "detail": detail}, data))
        return

    # Check for exit transition
    exit_info = result.get("exit")
    if exit_info:
        await _handle_exit_transition(
            websocket, data, game, entity_id, entity, player_info,
            room, room_key, exit_info, old_x, old_y,
        )
        return

    # Normal move — broadcast to all players in room (including mover)
    await game.connection_manager.broadcast_to_room(
        room_key,
        {
            "type": "entity_moved",
            "entity_id": entity_id,
            "x": result["x"],
            "y": result["y"],
        },
    )

    # Proximity notification — notify mover of nearby interactive objects
    nearby = _find_nearby_objects(room, result["x"], result["y"])
    if nearby:
        await websocket.send_json(with_request_id({"type": "nearby_objects", "objects": nearby}, data))

    # Check for mob encounter — initiate combat
    mob_encounter = result.get("mob_encounter")
    if mob_encounter:
        await _handle_mob_encounter(
            websocket, game, entity_id, entity, player_info, room, mob_encounter,
        )


async def _handle_mob_encounter(
    websocket: WebSocket,
    game: Game,
    entity_id: str,
    entity,
    player_info,
    room,
    mob_encounter: dict,
) -> None:
    """Initiate combat when player encounters a hostile mob."""
    from server.combat.service import initiate_combat

    npc_id = mob_encounter["entity_id"]
    npc = room.get_npc(npc_id)
    if npc is None:
        return

    # Atomically check-and-set npc.in_combat under lock to prevent TOCTOU races
    async with npc._lock:
        if not npc.is_alive or npc.in_combat:
            return
        npc.in_combat = True

    try:
        result = await initiate_combat(
            entity_id=entity_id,
            npc=npc,
            room_key=player_info.room_key,
            game=game,
        )
        if result is None:
            return

        # Broadcast combat_start to all participants
        for pid in result.participant_ids:
            ws = game.connection_manager.get_websocket(pid)
            if ws:
                await ws.send_json({"type": "combat_start", **result.state})
    except Exception:
        npc.in_combat = False
        raise


async def _handle_exit_transition(
    websocket: WebSocket,
    data: dict,
    game: Game,
    entity_id: str,
    entity,
    player_info,
    old_room,
    old_room_key: str,
    exit_info: dict,
    old_x: int,
    old_y: int,
) -> None:
    """Handle room transition when player steps on an exit tile."""
    target_room_key = exit_info["target_room"]

    # Load target room (from memory or DB)
    target_room = game.room_manager.get_room(target_room_key)
    if target_room is None:
        async with game.transaction() as session:
            room_db = await room_repo.get_by_key(session, target_room_key)
        if room_db is None:
            # Revert position and send error
            entity.x, entity.y = old_x, old_y
            await websocket.send_json(
                with_request_id({"type": "error", "detail": "Exit leads nowhere"}, data)
            )
            return
        target_room = game.room_manager.load_room(room_db)

    # Cancel active trade before leaving room
    cancelled = game.trade_manager.cancel_trades_for(entity_id)
    if cancelled:
        other_id = (
            cancelled.player_b
            if cancelled.player_a == entity_id
            else cancelled.player_a
        )
        await game.connection_manager.send_to_player(
            other_id,
            {
                "type": "trade_result",
                "status": "cancelled",
                "reason": "Trade cancelled \u2014 player left the room",
            },
        )

    # Remove from current room
    old_room.remove_entity(entity_id)

    # Broadcast entity_left to old room
    await game.connection_manager.broadcast_to_room(
        old_room_key,
        {"type": "entity_left", "entity_id": entity_id},
        exclude=entity_id,
    )

    # Determine entry position in target room (validate walkability)
    entry_x = exit_info.get("entry_x")
    entry_y = exit_info.get("entry_y")
    if entry_x is None or entry_y is None or not target_room.is_walkable(entry_x, entry_y):
        entry_x, entry_y = find_spawn_point(target_room, target_room_key, entity.name)

    # Place entity in new room
    entity.x = entry_x
    entity.y = entry_y
    target_room.add_entity(entity)

    # Update tracking
    player_info.room_key = target_room_key
    game.connection_manager.update_room(entity_id, target_room_key)

    # Save position to DB
    async with game.transaction() as session:
        await player_repo.update_position(
            session, entity.player_db_id, target_room_key, entry_x, entry_y
        )

    # Send new room state to transitioning player
    await websocket.send_json(with_request_id({"type": "room_state", **target_room.get_state()}, data))

    # Exploration XP — first visit to this room
    visited_rooms = player_info.visited_rooms
    if target_room_key not in visited_rooms:
        visited_rooms.add(target_room_key)
        player_info.visited_rooms = visited_rooms
        await grant_xp(
            entity_id, entity, settings.XP_EXPLORATION_REWARD,
            "exploration", f"Discovered {target_room.name}", game,
        )
        async with game.transaction() as session:
            await player_repo.update_visited_rooms(
                session, entity.player_db_id, list(visited_rooms),
            )

    # Notify other players in new room
    entity_data = {
        "id": entity.id,
        "name": entity.name,
        "x": entity.x,
        "y": entity.y,
        "level": entity.stats.get("level", 1),
    }
    await game.connection_manager.broadcast_to_room(
        target_room_key,
        {"type": "entity_entered", "entity": entity_data},
        exclude=entity_id,
    )
