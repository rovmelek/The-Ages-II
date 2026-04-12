"""Movement handler for WebSocket clients."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import WebSocket

from server.core.config import settings
from server.core.xp import grant_xp
from server.net.auth_middleware import requires_auth
from server.net.schemas import with_request_id
from server.player import repo as player_repo
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


async def _cancel_trade_for(entity_id: str, game: Game) -> None:
    """Cancel any active trade for a player and notify the other party."""
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
                "reason": "Trade cancelled \u2014 player entered combat",
            },
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
        # Cancel active trade before entering combat
        await _cancel_trade_for(entity_id, game)

        room_key = player_info.room_key

        # Gather eligible party members in the same room
        all_player_ids = [entity_id]
        party = game.party_manager.get_party(entity_id)
        if party is not None:
            for mid in party.members:
                if mid == entity_id:
                    continue
                mid_info = game.player_manager.get_session(mid)
                if mid_info is None:
                    continue
                if game.connection_manager.get_room(mid) != room_key:
                    continue
                if mid_info.entity.in_combat:
                    continue
                all_player_ids.append(mid)
                # Cancel trades for pulled-in party members
                await _cancel_trade_for(mid, game)

        # Load card definitions for player deck
        from server.combat.cards.card_def import CardDef
        from server.combat.cards import card_repo

        card_defs: list[CardDef] = []
        async with game.transaction() as session:
            cards = await card_repo.get_all(session)
            card_defs = [CardDef.from_db(c) for c in cards]

        # Fallback: if no cards in DB, create basic cards
        if not card_defs:
            card_defs = [
                CardDef(card_key=f"basic_attack_{i}", name="Basic Attack", cost=1,
                        effects=[{"type": "damage", "value": 10}])
                for i in range(10)
            ]

        # Create combat instance (store NPC reference for death/release on combat end)
        mob_stats = dict(npc.stats) if npc.stats else {"hp": 50, "max_hp": 50, "attack": 10}
        tmpl = game.npc_templates.get(npc.npc_key)
        mob_hit_dice = tmpl.get("hit_dice", 0) if tmpl else 0

        # Scale mob HP by party size for multi-player combat
        party_size = len(all_player_ids)
        if party_size > 1:
            mob_stats["hp"] *= party_size
            mob_stats["max_hp"] *= party_size

        # Build player stats map for all participants
        player_stats_map: dict[str, dict] = {}
        for pid in all_player_ids:
            p_info = game.player_manager.get_session(pid)
            if p_info is None:
                continue
            p_stats = dict(p_info.entity.stats)
            p_stats.setdefault("hp", settings.DEFAULT_BASE_HP)
            p_stats.setdefault("max_hp", p_stats["hp"])
            p_stats.setdefault("attack", settings.DEFAULT_ATTACK)
            p_stats.setdefault("shield", 0)
            player_stats_map[pid] = p_stats

        instance = game.combat_manager.start_combat(
            npc.name, mob_stats, all_player_ids, player_stats_map, card_defs,
            npc_id=npc_id, room_key=room_key, mob_hit_dice=mob_hit_dice,
        )

        # Register turn timeout callback and start the first timer
        from server.net.handlers.combat import make_turn_timeout_callback
        instance.set_turn_timeout_callback(make_turn_timeout_callback(game))
        instance.start_turn_timer()

        # Mark all participants as in combat and send combat_start
        state = instance.get_state()
        for pid in all_player_ids:
            p_info = game.player_manager.get_session(pid)
            if p_info:
                p_info.entity.in_combat = True
            ws = game.connection_manager.get_websocket(pid)
            if ws:
                await ws.send_json({"type": "combat_start", **state})
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
        entry_x, entry_y = target_room.get_player_spawn()
    if not target_room.is_walkable(entry_x, entry_y):
        entry_x, entry_y = target_room.find_first_walkable()
    if not target_room.is_walkable(entry_x, entry_y):
        logger.warning(
            "Room %s has no walkable tile; placing %s at (%d, %d)",
            target_room_key, entity.name, entry_x, entry_y,
        )

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
