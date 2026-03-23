"""Combat action handlers for WebSocket clients."""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import WebSocket

if TYPE_CHECKING:
    from server.app import Game


async def handle_play_card(
    websocket: WebSocket, data: dict, *, game: Game
) -> None:
    """Handle the 'play_card' action during combat."""
    entity_id = game.connection_manager.get_entity_id(websocket)
    if entity_id is None:
        await websocket.send_json({"type": "error", "detail": "Not logged in"})
        return

    instance = game.combat_manager.get_player_instance(entity_id)
    if instance is None:
        await websocket.send_json({"type": "error", "detail": "Not in combat"})
        return

    card_key = data.get("card_key", "")
    if not card_key:
        await websocket.send_json(
            {"type": "error", "detail": "Missing card_key"}
        )
        return

    try:
        result = instance.play_card(entity_id, card_key)
    except ValueError as e:
        await websocket.send_json({"type": "error", "detail": str(e)})
        return

    # Broadcast updated combat state with action result to all participants
    state = instance.get_state()
    for eid in instance.participants:
        ws = game.connection_manager.get_websocket(eid)
        if ws:
            await ws.send_json({"type": "combat_turn", "result": result, **state})


async def handle_pass_turn(
    websocket: WebSocket, data: dict, *, game: Game
) -> None:
    """Handle the 'pass_turn' action during combat."""
    entity_id = game.connection_manager.get_entity_id(websocket)
    if entity_id is None:
        await websocket.send_json({"type": "error", "detail": "Not logged in"})
        return

    instance = game.combat_manager.get_player_instance(entity_id)
    if instance is None:
        await websocket.send_json({"type": "error", "detail": "Not in combat"})
        return

    try:
        result = instance.pass_turn(entity_id)
    except ValueError as e:
        await websocket.send_json({"type": "error", "detail": str(e)})
        return

    # Broadcast updated combat state with action result to all participants
    state = instance.get_state()
    for eid in instance.participants:
        ws = game.connection_manager.get_websocket(eid)
        if ws:
            await ws.send_json({"type": "combat_turn", "result": result, **state})
