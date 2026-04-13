"""Inventory and item usage handlers for WebSocket clients."""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import WebSocket

from server.core.config import settings
from server.core.constants import EffectType
from server.net.auth_middleware import requires_auth
from server.net.schemas import with_request_id
from server.player import repo as player_repo
from server.player.session import PlayerSession

if TYPE_CHECKING:
    from server.app import Game


@requires_auth
async def handle_inventory(
    websocket: WebSocket, data: dict, *, game: Game,
    entity_id: str, player_info: PlayerSession,
) -> None:
    """Handle the 'inventory' action — return player's inventory."""
    inventory = player_info.inventory
    if inventory is None:
        await websocket.send_json(with_request_id({"type": "inventory", "items": []}, data))
        return

    await websocket.send_json(with_request_id({
        "type": "inventory",
        "items": inventory.get_inventory(),
    }, data))


@requires_auth
async def handle_use_item(
    websocket: WebSocket, data: dict, *, game: Game,
    entity_id: str, player_info: PlayerSession,
) -> None:
    """Handle the 'use_item' action outside of combat."""
    entity = player_info.entity

    # Cannot use items this way during combat
    if entity.in_combat:
        await websocket.send_json(
            with_request_id({"type": "error", "detail": "Cannot use items this way during combat"}, data)
        )
        return

    item_key = data.get("item_key", "")

    inventory = player_info.inventory
    if inventory is None or not inventory.has_item(item_key):
        await websocket.send_json(with_request_id({"type": "error", "detail": "Item not in inventory"}, data))
        return

    item_def = inventory.get_item(item_key)
    if not item_def.usable_outside_combat:
        await websocket.send_json(with_request_id({"type": "error", "detail": "This item cannot be used"}, data))
        return

    # Resolve effects through EffectRegistry
    effect_results = []
    player_stats = entity.stats
    player_stats.setdefault("hp", settings.DEFAULT_BASE_HP)
    player_stats.setdefault("max_hp", settings.DEFAULT_BASE_HP)
    player_stats.setdefault("energy", settings.DEFAULT_BASE_ENERGY)
    player_stats.setdefault("max_energy", settings.DEFAULT_BASE_ENERGY)
    player_stats.setdefault("shield", 0)
    for effect in item_def.effects:
        result = await game.effect_registry.resolve(
            effect, player_stats, player_stats
        )
        effect_results.append(result)

    # Consume one charge (removes one from quantity)
    inventory.use_charge(item_key)

    # Persist inventory and stats to DB
    db_id = player_info.db_id
    async with game.transaction() as session:
        await player_repo.update_inventory(session, db_id, inventory.to_dict())
        await player_repo.update_stats(session, db_id, entity.stats)

    await websocket.send_json(with_request_id({
        "type": "item_used",
        "item_key": item_key,
        "item_name": item_def.name,
        "effect_results": effect_results,
    }, data))

    # Send stats_update when HP or energy changed
    stat_affecting = {EffectType.HEAL, EffectType.RESTORE_ENERGY}
    if any(r.get("type") in stat_affecting for r in effect_results):
        await game.connection_manager.send_to_player_seq(entity_id, {
            "type": "stats_update",
            "hp": entity.stats["hp"],
            "max_hp": entity.stats["max_hp"],
            "energy": entity.stats.get("energy", 0),
            "max_energy": entity.stats.get("max_energy", 0),
        })
