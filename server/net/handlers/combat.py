"""Combat action handlers for WebSocket clients."""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import WebSocket

if TYPE_CHECKING:
    from server.app import Game


async def _broadcast_combat_state(instance, result: dict, game: Game) -> None:
    """Broadcast combat turn state to all participants."""
    state = instance.get_state()
    for eid in instance.participants:
        ws = game.connection_manager.get_websocket(eid)
        if ws:
            await ws.send_json({"type": "combat_turn", "result": result, **state})


async def _check_combat_end(instance, game: Game) -> None:
    """Check if combat is finished and broadcast end result if so."""
    end_result = instance.get_combat_end_result()
    if end_result is None:
        return

    # Broadcast combat_end to all participants before cleanup
    participant_ids = list(instance.participants)
    for eid in participant_ids:
        ws = game.connection_manager.get_websocket(eid)
        if ws:
            await ws.send_json({"type": "combat_end", **end_result})
        # Mark player as not in combat
        player_info = game.player_entities.get(eid)
        if player_info:
            player_info["entity"].in_combat = False

    # Clean up: remove instance and all player mappings
    game.combat_manager.remove_instance(instance.instance_id)


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
        result = await instance.play_card(entity_id, card_key)
    except ValueError as e:
        await websocket.send_json({"type": "error", "detail": str(e)})
        return

    # Broadcast updated combat state with action result to all participants
    await _broadcast_combat_state(instance, result, game)

    # Check if combat has ended
    await _check_combat_end(instance, game)


async def handle_flee(
    websocket: WebSocket, data: dict, *, game: Game
) -> None:
    """Handle the 'flee' action during combat."""
    entity_id = game.connection_manager.get_entity_id(websocket)
    if entity_id is None:
        await websocket.send_json({"type": "error", "detail": "Not logged in"})
        return

    instance = game.combat_manager.get_player_instance(entity_id)
    if instance is None:
        await websocket.send_json({"type": "error", "detail": "Not in combat"})
        return

    # Dead players cannot flee
    stats = instance.participant_stats.get(entity_id)
    if stats and stats["hp"] <= 0:
        await websocket.send_json({"type": "error", "detail": "You are dead"})
        return

    # Remove from combat instance and player mapping
    instance.remove_participant(entity_id)
    game.combat_manager.remove_player(entity_id)

    # Mark player as not in combat
    player_info = game.player_entities.get(entity_id)
    if player_info:
        player_info["entity"].in_combat = False

    # Notify the fleeing player
    await websocket.send_json({"type": "combat_fled"})

    # If participants remain, broadcast updated state
    if instance.participants:
        state = instance.get_state()
        for eid in instance.participants:
            ws = game.connection_manager.get_websocket(eid)
            if ws:
                await ws.send_json({"type": "combat_update", **state})
    else:
        # Last player fled — clean up instance
        game.combat_manager.remove_instance(instance.instance_id)


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
        result = await instance.pass_turn(entity_id)
    except ValueError as e:
        await websocket.send_json({"type": "error", "detail": str(e)})
        return

    # Broadcast updated combat state with action result to all participants
    await _broadcast_combat_state(instance, result, game)

    # Check if combat has ended
    await _check_combat_end(instance, game)
