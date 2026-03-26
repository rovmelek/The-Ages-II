"""Movement handler for WebSocket clients."""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import WebSocket

from server.core.database import async_session
from server.player import repo as player_repo
from server.room import repo as room_repo

if TYPE_CHECKING:
    from server.app import Game


async def handle_move(websocket: WebSocket, data: dict, *, game: Game) -> None:
    """Handle the 'move' action: move player in a direction on the tile grid."""
    entity_id = game.connection_manager.get_entity_id(websocket)
    if entity_id is None:
        await websocket.send_json({"type": "error", "detail": "Not logged in"})
        return

    player_info = game.player_entities.get(entity_id)
    if player_info is None:
        await websocket.send_json({"type": "error", "detail": "Not logged in"})
        return

    entity = player_info["entity"]
    room_key = player_info["room_key"]

    # Cannot move while in combat
    if entity.in_combat:
        await websocket.send_json(
            {"type": "error", "detail": "Cannot move while in combat"}
        )
        return

    direction = data.get("direction", "")

    room = game.room_manager.get_room(room_key)
    if room is None:
        await websocket.send_json({"type": "error", "detail": "Room not found"})
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
        await websocket.send_json({"type": "error", "detail": detail})
        return

    # Check for exit transition
    exit_info = result.get("exit")
    if exit_info:
        await _handle_exit_transition(
            websocket, game, entity_id, entity, player_info,
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
    player_info: dict,
    room,
    mob_encounter: dict,
) -> None:
    """Initiate combat when player encounters a hostile mob."""
    npc_id = mob_encounter["entity_id"]
    npc = room.get_npc(npc_id)
    if npc is None or not npc.is_alive or npc.in_combat:
        return  # Dead or already in combat

    # Mark NPC as in combat (stays alive until victory)
    npc.in_combat = True

    # Load card definitions for player deck
    from server.combat.cards.card_def import CardDef
    from server.combat.cards import card_repo

    card_defs: list[CardDef] = []
    async with async_session() as session:
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
    room_key = player_info["room_key"]
    instance = game.combat_manager.create_instance(
        npc.name, mob_stats, npc_id=npc_id, room_key=room_key
    )
    # Ensure player stats have required combat keys
    player_stats = dict(entity.stats)
    player_stats.setdefault("hp", 100)
    player_stats.setdefault("max_hp", player_stats["hp"])
    player_stats.setdefault("attack", 10)
    player_stats.setdefault("shield", 0)
    instance.add_participant(entity_id, player_stats, card_defs)
    game.combat_manager.add_player_to_instance(entity_id, instance.instance_id)

    # Mark player as in combat
    entity.in_combat = True

    # Send combat_start to player
    state = instance.get_state()
    await websocket.send_json({"type": "combat_start", **state})


async def _handle_exit_transition(
    websocket: WebSocket,
    game: Game,
    entity_id: str,
    entity,
    player_info: dict,
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
        async with async_session() as session:
            room_db = await room_repo.get_by_key(session, target_room_key)
        if room_db is None:
            # Revert position and send error
            entity.x, entity.y = old_x, old_y
            await websocket.send_json(
                {"type": "error", "detail": "Exit leads nowhere"}
            )
            return
        target_room = game.room_manager.load_room(room_db)

    # Remove from current room
    old_room.remove_entity(entity_id)

    # Broadcast entity_left to old room
    await game.connection_manager.broadcast_to_room(
        old_room_key,
        {"type": "entity_left", "entity_id": entity_id},
        exclude=entity_id,
    )

    # Determine entry position in target room
    entry_x = exit_info.get("entry_x")
    entry_y = exit_info.get("entry_y")
    if entry_x is None or entry_y is None:
        entry_x, entry_y = target_room.get_player_spawn()

    # Place entity in new room
    entity.x = entry_x
    entity.y = entry_y
    target_room.add_entity(entity)

    # Update tracking
    player_info["room_key"] = target_room_key
    game.connection_manager.update_room(entity_id, target_room_key)

    # Save position to DB
    async with async_session() as session:
        await player_repo.update_position(
            session, entity.player_db_id, target_room_key, entry_x, entry_y
        )

    # Send new room state to transitioning player
    await websocket.send_json({"type": "room_state", **target_room.get_state()})

    # Notify other players in new room
    entity_data = {
        "id": entity.id,
        "name": entity.name,
        "x": entity.x,
        "y": entity.y,
    }
    await game.connection_manager.broadcast_to_room(
        target_room_key,
        {"type": "entity_entered", "entity": entity_data},
        exclude=entity_id,
    )
