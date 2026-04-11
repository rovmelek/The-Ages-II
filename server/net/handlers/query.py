"""Query handlers for WebSocket clients."""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import WebSocket

if TYPE_CHECKING:
    from server.app import Game

_SCAN_OFFSETS = [
    (0, 0, "here"),
    (0, -1, "up"),
    (0, 1, "down"),
    (-1, 0, "left"),
    (1, 0, "right"),
]


async def handle_look(
    websocket: WebSocket, data: dict, *, game: Game
) -> None:
    """Handle the 'look' action — return nearby objects, NPCs, and players."""
    entity_id = game.connection_manager.get_entity_id(websocket)
    if entity_id is None:
        await websocket.send_json({"type": "error", "detail": "Not logged in"})
        return

    player_info = game.player_entities.get(entity_id)
    if player_info is None:
        await websocket.send_json({"type": "error", "detail": "Not logged in"})
        return

    entity = player_info["entity"]
    room = game.room_manager.get_room(player_info["room_key"])
    if room is None:
        await websocket.send_json({"type": "error", "detail": "Room not found"})
        return

    objects, npcs, players = [], [], []
    for dx, dy, label in _SCAN_OFFSETS:
        tx, ty = entity.x + dx, entity.y + dy
        if tx < 0 or ty < 0 or tx >= room.width or ty >= room.height:
            continue
        for obj in room._interactive_objects.values():
            if obj["x"] == tx and obj["y"] == ty:
                objects.append({"id": obj["id"], "type": obj["type"], "direction": label})
        for npc in room._npcs.values():
            if npc.x == tx and npc.y == ty:
                npcs.append({"name": npc.name, "alive": npc.is_alive, "direction": label})
        for e in room._entities.values():
            if e.id != entity_id and e.x == tx and e.y == ty:
                players.append({"name": e.name, "direction": label})

    await websocket.send_json({
        "type": "look_result",
        "objects": objects,
        "npcs": npcs,
        "players": players,
    })


async def handle_who(
    websocket: WebSocket, data: dict, *, game: Game
) -> None:
    """Handle the 'who' action — return all players in the current room."""
    entity_id = game.connection_manager.get_entity_id(websocket)
    if entity_id is None:
        await websocket.send_json({"type": "error", "detail": "Not logged in"})
        return

    player_info = game.player_entities.get(entity_id)
    if player_info is None:
        await websocket.send_json({"type": "error", "detail": "Not logged in"})
        return

    room_key = player_info["room_key"]
    room = game.room_manager.get_room(room_key)
    if room is None:
        await websocket.send_json({"type": "error", "detail": "Room not found"})
        return

    players = [
        {"name": e.name, "x": e.x, "y": e.y}
        for e in room._entities.values()
    ]

    await websocket.send_json({
        "type": "who_result",
        "room": room_key,
        "players": players,
    })


async def handle_stats(
    websocket: WebSocket, data: dict, *, game: Game
) -> None:
    """Handle the 'stats' action — return the player's current stats."""
    entity_id = game.connection_manager.get_entity_id(websocket)
    if entity_id is None:
        await websocket.send_json({"type": "error", "detail": "Not logged in"})
        return

    player_info = game.player_entities.get(entity_id)
    if player_info is None:
        await websocket.send_json({"type": "error", "detail": "Not logged in"})
        return

    stats = player_info["entity"].stats
    await websocket.send_json({
        "type": "stats_result",
        "stats": {
            "hp": stats.get("hp", 100),
            "max_hp": stats.get("max_hp", 100),
            "attack": stats.get("attack", 10),
            "xp": stats.get("xp", 0),
        },
    })


async def handle_help_actions(
    websocket: WebSocket, data: dict, *, game: Game
) -> None:
    """Handle the 'help_actions' action — return list of registered actions."""
    entity_id = game.connection_manager.get_entity_id(websocket)
    if entity_id is None:
        await websocket.send_json({"type": "error", "detail": "Not logged in"})
        return

    player_info = game.player_entities.get(entity_id)
    if player_info is None:
        await websocket.send_json({"type": "error", "detail": "Not logged in"})
        return

    actions = sorted(game.router._handlers.keys())
    await websocket.send_json({
        "type": "help_result",
        "actions": actions,
    })
