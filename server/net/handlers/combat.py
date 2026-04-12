"""Combat action handlers for WebSocket clients."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from fastapi import WebSocket

from server.core.config import settings
from server.core.xp import grant_xp
from server.items.item_def import ItemDef
from server.items import item_repo as items_repo
from server.items.loot import generate_loot
from server.player import repo as player_repo

if TYPE_CHECKING:
    from server.app import Game


async def _sync_combat_stats(instance, game: Game) -> None:
    """Sync combat participant stats back to entities and persist to DB."""
    for eid in instance.participants:
        player_info = game.player_entities.get(eid)
        if player_info is None:
            continue
        combat_stats = instance.participant_stats.get(eid)
        if combat_stats is None:
            continue
        entity = player_info["entity"]
        # Update entity stats from combat (exclude shield — combat-only)
        for key in ("hp", "max_hp"):
            if key in combat_stats:
                entity.stats[key] = combat_stats[key]
        # Persist to DB
        async with game.transaction() as session:
            await player_repo.update_stats(session, entity.player_db_id, entity.stats)


async def _broadcast_combat_state(instance, result: dict, game: Game) -> None:
    """Broadcast combat turn state to all participants."""
    # Sync stats back to entities and DB after each action
    await _sync_combat_stats(instance, game)

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
    rewards_per_player = end_result.get("rewards_per_player", {})

    # Apply party XP bonus when 2+ participants at victory
    if end_result.get("victory") and len(participant_ids) >= 2:
        bonus_multiplier = 1 + settings.XP_PARTY_BONUS_PERCENT / 100
        for eid in rewards_per_player:
            base_xp = rewards_per_player[eid].get("xp", 0)
            rewards_per_player[eid]["xp"] = math.floor(base_xp * bonus_multiplier)

    # Resolve loot table key before kill_npc (NPC data still accessible)
    loot_table_key = ""
    if end_result.get("victory") and instance.npc_id and instance.room_key:
        room = game.room_manager.get_room(instance.room_key)
        npc = room.get_npc(instance.npc_id) if room else None
        loot_table_key = npc.loot_table if npc else ""

    # Batch-load item defs if any loot will be generated
    item_defs: dict[str, ItemDef] = {}
    if loot_table_key:
        async with game.transaction() as session:
            all_items = await items_repo.get_all(session)
        item_defs = {i.item_key: ItemDef.from_db(i) for i in all_items}

    # Per-player loot tracking for combat_end messages
    player_loot: dict[str, list[dict]] = {}

    for eid in participant_ids:
        player_info = game.player_entities.get(eid)
        if player_info:
            entity = player_info["entity"]
            entity.in_combat = False
            # Reset combat-only transient stats
            entity.stats.pop("shield", None)
            entity.stats.pop("energy", None)
            entity.stats.pop("max_energy", None)

            # Sync final combat stats (hp etc.) back from instance FIRST
            combat_stats = instance.participant_stats.get(eid)
            if combat_stats:
                for key in ("hp", "max_hp"):
                    if key in combat_stats:
                        entity.stats[key] = combat_stats[key]

            is_alive = entity.stats.get("hp", 0) > 0

            # Dead players get zero rewards in their combat_end message
            if not is_alive:
                rewards_per_player[eid] = {"xp": 0}

            # Apply per-player XP reward on victory — skip dead players
            if end_result.get("victory") and is_alive:
                xp_reward = rewards_per_player.get(eid, {}).get("xp", 0)
                if xp_reward:
                    npc_name = end_result.get("mob_name", "enemy")
                    await grant_xp(eid, entity, xp_reward, "combat", npc_name, game, apply_cha_bonus=False)

            # Independent loot roll per surviving participant
            if end_result.get("victory") and is_alive and loot_table_key:
                loot_items = generate_loot(loot_table_key)
                if loot_items:
                    player_loot[eid] = loot_items
                    db_id = player_info["db_id"]
                    async with game.transaction() as session:
                        player = await player_repo.get_by_id(session, db_id)
                        if player is not None:
                            db_inv = dict(player.inventory or {})
                            for item in loot_items:
                                key = item["item_key"]
                                db_inv[key] = db_inv.get(key, 0) + item["quantity"]
                            await player_repo.update_inventory(session, db_id, db_inv)
                    runtime_inv = player_info.get("inventory")
                    if runtime_inv:
                        for item in loot_items:
                            idef = item_defs.get(item["item_key"])
                            if idef:
                                runtime_inv.add_item(idef, item["quantity"])

            # Persist stats to DB
            async with game.transaction() as session:
                await player_repo.update_stats(
                    session, entity.player_db_id, entity.stats
                )

        ws = game.connection_manager.get_websocket(eid)
        if ws:
            # Send per-player combat_end with individual rewards and loot
            player_end_result = dict(end_result)
            player_end_result["rewards"] = rewards_per_player.get(eid, {})
            player_end_result.pop("rewards_per_player", None)
            if eid in player_loot:
                player_end_result["loot"] = player_loot[eid]
            else:
                player_end_result.pop("loot", None)
            await ws.send_json({"type": "combat_end", **player_end_result})

    # Update NPC state based on combat outcome
    if instance.npc_id and instance.room_key:
        if end_result.get("victory"):
            # Victory: kill the NPC and schedule respawn
            await game.kill_npc(instance.room_key, instance.npc_id)
            # Broadcast updated room state so all players see NPC death
            room = game.room_manager.get_room(instance.room_key)
            if room:
                await game.connection_manager.broadcast_to_room(
                    instance.room_key,
                    {"type": "room_state", **room.get_state()},
                )
        else:
            # Defeat: release NPC back to available
            room = game.room_manager.get_room(instance.room_key)
            if room:
                npc = room.get_npc(instance.npc_id)
                if npc:
                    npc.in_combat = False

    # On defeat: respawn all defeated players in town_square
    if not end_result.get("victory"):
        for eid in participant_ids:
            player_info = game.player_entities.get(eid)
            if player_info:
                entity = player_info["entity"]
                if entity.stats.get("hp", 0) <= 0:
                    await game.respawn_player(eid)

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
        # Last player fled — release NPC and clean up instance
        if instance.npc_id and instance.room_key:
            room = game.room_manager.get_room(instance.room_key)
            if room:
                npc = room.get_npc(instance.npc_id)
                if npc:
                    npc.in_combat = False
        game.combat_manager.remove_instance(instance.instance_id)


async def handle_use_item_combat(
    websocket: WebSocket, data: dict, *, game: Game
) -> None:
    """Handle 'use_item' action during combat — uses item as turn action."""
    entity_id = game.connection_manager.get_entity_id(websocket)
    if entity_id is None:
        await websocket.send_json({"type": "error", "detail": "Not logged in"})
        return

    instance = game.combat_manager.get_player_instance(entity_id)
    if instance is None:
        await websocket.send_json({"type": "error", "detail": "Not in combat"})
        return

    item_key = data.get("item_key", "")
    if not item_key:
        await websocket.send_json({"type": "error", "detail": "Missing item_key"})
        return

    # Get player inventory
    player_info = game.player_entities.get(entity_id)
    if player_info is None:
        await websocket.send_json({"type": "error", "detail": "Not logged in"})
        return

    inventory = player_info.get("inventory")
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
    db_id = player_info["db_id"]
    async with game.transaction() as session:
        await player_repo.update_inventory(session, db_id, inventory.to_dict())

    # Broadcast updated combat state with action result to all participants
    await _broadcast_combat_state(instance, result, game)

    # Check if combat has ended
    await _check_combat_end(instance, game)


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
