"""Combat action handlers for WebSocket clients."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import WebSocket

from server.combat import service
from server.net.auth_middleware import requires_auth
from server.player import repo as player_repo
from server.player.session import PlayerSession

if TYPE_CHECKING:
    from server.app import Game

logger = logging.getLogger(__name__)


async def _broadcast_combat_state(instance, result: dict, game: Game) -> None:
    """Broadcast combat turn state to all participants."""
    # Sync stats back to entities and DB after each action
    await service.sync_combat_stats(instance, game)

    state = instance.get_state()
    for eid in instance.participants:
        ws = game.connection_manager.get_websocket(eid)
        if ws:
            await ws.send_json({"type": "combat_turn", "result": result, **state})


async def _send_combat_end_message(
    eid: str, end_result: dict, rewards_per_player: dict,
    player_loot: dict[str, list[dict]], instance, game: Game
) -> None:
    """Build and send per-player combat_end message."""
    ws = game.connection_manager.get_websocket(eid)
    if not ws:
        return
    player_end_result = dict(end_result)
    player_end_result["rewards"] = rewards_per_player.get(eid, {})
    player_end_result.pop("rewards_per_player", None)
    if eid in player_loot:
        player_end_result["loot"] = player_loot[eid]
    else:
        player_end_result.pop("loot", None)
    if end_result.get("victory") and instance.npc_id:
        player_end_result["defeated_npc_id"] = instance.npc_id
    await ws.send_json({"type": "combat_end", **player_end_result})


async def _check_combat_end(instance, game: Game) -> None:
    """Check if combat ended, send messages and run post-combat actions."""
    combat_end = await service.finalize_combat(instance, game)
    if combat_end is None:
        return

    # Send per-player combat_end messages FIRST (before NPC kill broadcasts room_state)
    for eid in combat_end.participant_ids:
        await _send_combat_end_message(
            eid, combat_end.end_result, combat_end.rewards_per_player,
            combat_end.player_loot, instance, game,
        )

    # Post-message actions: NPC outcome, respawn, cleanup
    await service.handle_npc_combat_outcome(instance, combat_end.end_result, game)
    await service.respawn_defeated_players(
        combat_end.participant_ids, combat_end.end_result, game,
    )
    game.combat_manager.remove_instance(instance.instance_id)


@requires_auth
async def handle_play_card(
    websocket: WebSocket, data: dict, *, game: Game,
    entity_id: str, player_info: PlayerSession,
) -> None:
    """Handle the 'play_card' action during combat."""
    instance = game.combat_manager.get_player_instance(entity_id)
    if instance is None:
        await websocket.send_json({"type": "error", "detail": "Not in combat"})
        return

    card_key = data.get("card_key", "")

    try:
        result = await instance.play_card(entity_id, card_key)
    except ValueError as e:
        await websocket.send_json({"type": "error", "detail": str(e)})
        return

    # Broadcast updated combat state with action result to all participants
    await _broadcast_combat_state(instance, result, game)

    # Check if combat has ended
    await _check_combat_end(instance, game)


@requires_auth
async def handle_flee(
    websocket: WebSocket, data: dict, *, game: Game,
    entity_id: str, player_info: PlayerSession,
) -> None:
    """Handle the 'flee' action during combat."""
    instance = game.combat_manager.get_player_instance(entity_id)
    if instance is None:
        await websocket.send_json({"type": "error", "detail": "Not in combat"})
        return

    # Dead players cannot flee
    stats = instance.participant_stats.get(entity_id)
    if stats and stats["hp"] <= 0:
        await websocket.send_json({"type": "error", "detail": "You are dead"})
        return

    # Delegate business logic to service
    outcome = service.handle_flee_outcome(instance, entity_id, player_info, game)

    # Notify the fleeing player
    await websocket.send_json({"type": "combat_fled"})

    # If participants remain, broadcast updated state
    if outcome.participants_remain:
        state = instance.get_state()
        for eid in instance.participants:
            ws = game.connection_manager.get_websocket(eid)
            if ws:
                await ws.send_json({"type": "combat_update", **state})


@requires_auth
async def handle_use_item_combat(
    websocket: WebSocket, data: dict, *, game: Game,
    entity_id: str, player_info: PlayerSession,
) -> None:
    """Handle 'use_item' action during combat — uses item as turn action."""
    instance = game.combat_manager.get_player_instance(entity_id)
    if instance is None:
        await websocket.send_json({"type": "error", "detail": "Not in combat"})
        return

    item_key = data.get("item_key", "")

    inventory = player_info.inventory
    if inventory is None or not inventory.has_item(item_key):
        await websocket.send_json({"type": "error", "detail": "Item not in inventory"})
        return

    item_def = inventory.get_item(item_key)
    if not item_def.usable_in_combat:
        await websocket.send_json(
            {"type": "error", "detail": "This item cannot be used in combat"}
        )
        return

    try:
        result = await instance.use_item(entity_id, item_def)
    except ValueError as e:
        await websocket.send_json({"type": "error", "detail": str(e)})
        return

    # Consume one charge from inventory and persist
    inventory.use_charge(item_key)
    db_id = player_info.db_id
    async with game.transaction() as session:
        await player_repo.update_inventory(session, db_id, inventory.to_dict())

    # Broadcast updated combat state with action result to all participants
    await _broadcast_combat_state(instance, result, game)

    # Check if combat has ended
    await _check_combat_end(instance, game)


@requires_auth
async def handle_pass_turn(
    websocket: WebSocket, data: dict, *, game: Game,
    entity_id: str, player_info: PlayerSession,
) -> None:
    """Handle the 'pass_turn' action during combat."""
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
