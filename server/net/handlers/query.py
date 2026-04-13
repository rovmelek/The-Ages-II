"""Query handlers for WebSocket clients."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import WebSocket

from server.core.config import settings
from server.core.constants import STAT_NAMES
from server.net.auth_middleware import requires_auth
from server.net.schemas import with_request_id
from server.player.session import PlayerSession

if TYPE_CHECKING:
    from server.app import Game

logger = logging.getLogger(__name__)

_SCAN_OFFSETS = [
    (0, 0, "here"),
    (0, -1, "up"),
    (0, 1, "down"),
    (-1, 0, "left"),
    (1, 0, "right"),
]


@requires_auth
async def handle_look(
    websocket: WebSocket, data: dict, *, game: Game,
    entity_id: str, player_info: PlayerSession,
) -> None:
    """Handle the 'look' action — return nearby objects, NPCs, and players."""
    entity = player_info.entity
    room = game.room_manager.get_room(player_info.room_key)
    if room is None:
        await websocket.send_json(with_request_id({"type": "error", "detail": "Room not found"}, data))
        return

    objects, npcs, players = [], [], []
    for dx, dy, label in _SCAN_OFFSETS:
        tx, ty = entity.x + dx, entity.y + dy
        if tx < 0 or ty < 0 or tx >= room.width or ty >= room.height:
            continue
        for obj in room.interactive_objects.values():
            if obj.x == tx and obj.y == ty:
                objects.append({"id": obj.id, "type": obj.type, "direction": label})
        for npc in room.npcs.values():
            if npc.x == tx and npc.y == ty:
                npcs.append({"name": npc.name, "alive": npc.is_alive, "direction": label})
        for e in room.entities.values():
            if e.id != entity_id and e.x == tx and e.y == ty:
                players.append({"name": e.name, "direction": label})

    await websocket.send_json(with_request_id({
        "type": "look_result",
        "objects": objects,
        "npcs": npcs,
        "players": players,
    }, data))


@requires_auth
async def handle_who(
    websocket: WebSocket, data: dict, *, game: Game,
    entity_id: str, player_info: PlayerSession,
) -> None:
    """Handle the 'who' action — return all players in the current room."""
    room_key = player_info.room_key
    room = game.room_manager.get_room(room_key)
    if room is None:
        await websocket.send_json(with_request_id({"type": "error", "detail": "Room not found"}, data))
        return

    players = [
        {"name": e.name, "x": e.x, "y": e.y}
        for e in room.entities.values()
    ]

    await websocket.send_json(with_request_id({
        "type": "who_result",
        "room": room_key,
        "players": players,
    }, data))


@requires_auth
async def handle_stats(
    websocket: WebSocket, data: dict, *, game: Game,
    entity_id: str, player_info: PlayerSession,
) -> None:
    """Handle the 'stats' action — return the player's current stats."""
    stats = player_info.entity.stats
    level = stats.get("level", 1)
    await websocket.send_json(with_request_id({
        "type": "stats_result",
        "stats": {
            "hp": stats.get("hp", settings.DEFAULT_BASE_HP),
            "max_hp": stats.get("max_hp", settings.DEFAULT_BASE_HP),
            "attack": stats.get("attack", settings.DEFAULT_ATTACK),
            "xp": stats.get("xp", 0),
            "xp_next": level * settings.XP_LEVEL_THRESHOLD_MULTIPLIER,
            "xp_for_next_level": level * settings.XP_LEVEL_THRESHOLD_MULTIPLIER,
            "xp_for_current_level": (level - 1) * settings.XP_LEVEL_THRESHOLD_MULTIPLIER,
            "level": level,
            **{s: stats.get(s, settings.DEFAULT_STAT_VALUE) for s in STAT_NAMES},
        },
    }, data))


@requires_auth
async def handle_help_actions(
    websocket: WebSocket, data: dict, *, game: Game,
    entity_id: str, player_info: PlayerSession,
) -> None:
    """Handle the 'help_actions' action — return actions grouped by category."""
    categories = {
        "Movement": ["move"],
        "Combat": ["play_card", "pass_turn", "flee", "use_item_combat"],
        "Items": ["inventory", "use_item", "interact"],
        "Social": ["chat", "trade", "party", "logout"],
        "Info": ["look", "who", "stats", "map", "help_actions", "level_up"],
    }
    await websocket.send_json(with_request_id({
        "type": "help_result",
        "categories": categories,
    }, data))


@requires_auth
async def handle_map(
    websocket: WebSocket, data: dict, *, game: Game,
    entity_id: str, player_info: PlayerSession,
) -> None:
    """Handle the 'map' action — return discovered rooms and connections."""
    visited_rooms = player_info.visited_rooms

    rooms = []
    connections = []
    for room_key in visited_rooms:
        room = game.room_manager.get_room(room_key)
        if room is None:
            logger.warning("Stale room_key %r in visited_rooms for %s", room_key, entity_id)
            continue
        rooms.append({"room_key": room.room_key, "name": room.name})
        for exit_info in room.exits:
            target_key = exit_info["target_room"]
            if target_key in visited_rooms:
                target_room = game.room_manager.get_room(target_key)
                to_name = target_room.name if target_room else "???"
            else:
                to_name = "???"
            connections.append({
                "from_room": room_key,
                "to_room": to_name,
                "direction": exit_info["direction"],
            })

    await websocket.send_json(with_request_id({
        "type": "map_data",
        "rooms": rooms,
        "connections": connections,
    }, data))
