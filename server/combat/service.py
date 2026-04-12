"""Combat service — business logic for combat resolution and end-of-combat orchestration."""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from server.core.config import settings
from server.core.xp import grant_xp
from server.items.item_def import ItemDef
from server.items import item_repo as items_repo
from server.player import repo as player_repo

if TYPE_CHECKING:
    from server.app import Game

logger = logging.getLogger(__name__)


async def sync_combat_stats(instance: Any, game: Game) -> None:
    """Sync combat participant stats back to entities and persist to DB."""
    for eid in instance.participants:
        player_info = game.player_manager.get_session(eid)
        if player_info is None:
            continue
        combat_stats = instance.participant_stats.get(eid)
        if combat_stats is None:
            continue
        entity = player_info.entity
        # Update entity stats from combat (exclude shield — combat-only)
        for key in ("hp", "max_hp"):
            if key in combat_stats:
                entity.stats[key] = combat_stats[key]
        # Persist to DB
        async with game.transaction() as session:
            await player_repo.update_stats(session, entity.player_db_id, entity.stats)


def clean_player_combat_stats(entity: Any, instance: Any, eid: str) -> bool:
    """Clear combat flags, sync final stats, return whether player is alive."""
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

    return entity.stats.get("hp", 0) > 0


async def award_combat_xp(
    eid: str, entity: Any, rewards_per_player: dict, end_result: dict, game: Game,
    session: Any = None,
) -> None:
    """Award XP to a surviving victor."""
    xp_reward = rewards_per_player.get(eid, {}).get("xp", 0)
    if xp_reward:
        npc_name = end_result.get("mob_name", "enemy")
        await grant_xp(eid, entity, xp_reward, "combat", npc_name, game, apply_cha_bonus=False, session=session)


async def distribute_combat_loot(
    eid: str, player_info: Any, loot_table_key: str, item_defs: dict[str, ItemDef], game: Game,
    session: Any = None,
) -> list[dict]:
    """Roll loot for a participant, persist to DB, update runtime inventory.

    Args:
        session: Optional DB session for transaction consolidation.
    """
    loot_items = list(game.loot_tables.get(loot_table_key, []))
    if not loot_items:
        return []

    db_id = player_info.db_id

    async def _persist_loot(s):
        player = await player_repo.get_by_id(s, db_id)
        if player is not None:
            db_inv = dict(player.inventory or {})
            for item in loot_items:
                key = item["item_key"]
                db_inv[key] = db_inv.get(key, 0) + item["quantity"]
            await player_repo.update_inventory(s, db_id, db_inv)

    if session is not None:
        await _persist_loot(session)
    else:
        async with game.transaction() as s:
            await _persist_loot(s)

    runtime_inv = player_info.inventory
    if runtime_inv:
        for item in loot_items:
            idef = item_defs.get(item["item_key"])
            if idef:
                runtime_inv.add_item(idef, item["quantity"])

    return loot_items


async def handle_npc_combat_outcome(instance: Any, end_result: dict, game: Game) -> None:
    """Kill NPC on victory (+ broadcast), or release NPC on defeat."""
    if not instance.npc_id or not instance.room_key:
        return
    if end_result.get("victory"):
        await game.kill_npc(instance.room_key, instance.npc_id)
        room = game.room_manager.get_room(instance.room_key)
        if room:
            await game.connection_manager.broadcast_to_room(
                instance.room_key,
                {"type": "room_state", **room.get_state()},
            )
    else:
        room = game.room_manager.get_room(instance.room_key)
        if room:
            npc = room.get_npc(instance.npc_id)
            if npc:
                npc.in_combat = False


async def respawn_defeated_players(
    participant_ids: list[str], end_result: dict, game: Game,
) -> None:
    """On defeat, respawn all dead players in town_square."""
    if end_result.get("victory"):
        return
    for eid in participant_ids:
        player_info = game.player_manager.get_session(eid)
        if player_info:
            entity = player_info.entity
            if entity.stats.get("hp", 0) <= 0:
                await game.respawn_player(eid)


@dataclass
class CombatEndResult:
    """Result of finalize_combat — data for the handler to send messages."""

    participant_ids: list[str]
    end_result: dict
    rewards_per_player: dict
    player_loot: dict[str, list[dict]] = field(default_factory=dict)


async def finalize_combat(instance: Any, game: Game) -> CombatEndResult | None:
    """Check if combat is finished and handle end-of-combat orchestration.

    Returns per-player data for message construction, or None if combat continues.
    """
    end_result = instance.get_combat_end_result()
    if end_result is None:
        return None

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
        player_info = game.player_manager.get_session(eid)
        if player_info:
            entity = player_info.entity
            is_alive = clean_player_combat_stats(entity, instance, eid)

            # Dead players get zero rewards in their combat_end message
            if not is_alive:
                rewards_per_player[eid] = {"xp": 0}

            # Consolidated transaction: XP + loot + stats in one DB round-trip
            # Per-participant isolation: each participant's failure is independent
            try:
                async with game.transaction() as session:
                    stats_persisted = False

                    # Award XP on victory — skip dead players
                    if end_result.get("victory") and is_alive:
                        await award_combat_xp(eid, entity, rewards_per_player, end_result, game, session=session)
                        stats_persisted = True  # grant_xp already called update_stats

                    # Distribute loot to surviving victors
                    if end_result.get("victory") and is_alive and loot_table_key:
                        loot = await distribute_combat_loot(eid, player_info, loot_table_key, item_defs, game, session=session)
                        if loot:
                            player_loot[eid] = loot

                    # Persist final stats (only if not already saved by XP grant)
                    if not stats_persisted:
                        await player_repo.update_stats(
                            session, entity.player_db_id, entity.stats
                        )
            except Exception:
                logger.exception(
                    "Failed to persist combat-end state for %s", eid
                )

    return CombatEndResult(
        participant_ids=participant_ids,
        end_result=end_result,
        rewards_per_player=rewards_per_player,
        player_loot=player_loot,
    )


@dataclass
class FleeOutcome:
    """Result of handle_flee_outcome — tells handler what messages to send."""

    participants_remain: bool


def handle_flee_outcome(instance: Any, entity_id: str, player_info: Any, game: Game) -> FleeOutcome:
    """Handle business logic of fleeing: remove participant, clean up if last."""
    # Remove from combat instance and player mapping
    instance.remove_participant(entity_id)
    game.combat_manager.remove_player(entity_id)

    # Mark player as not in combat
    player_info.entity.in_combat = False

    if instance.participants:
        return FleeOutcome(participants_remain=True)

    # Last player fled — release NPC and clean up instance
    if instance.npc_id and instance.room_key:
        room = game.room_manager.get_room(instance.room_key)
        if room:
            npc = room.get_npc(instance.npc_id)
            if npc:
                npc.in_combat = False
    game.combat_manager.remove_instance(instance.instance_id)

    return FleeOutcome(participants_remain=False)
