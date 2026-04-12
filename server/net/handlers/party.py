"""Party action handler for WebSocket clients."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import WebSocket

from server.core.config import settings
from server.net.auth_middleware import requires_auth
from server.player.session import PlayerSession

if TYPE_CHECKING:
    from server.app import Game

logger = logging.getLogger(__name__)


def _members_share_combat(game: Game, members: list[str]) -> bool:
    """Check if any two party members share an active combat instance."""
    instances: set[str] = set()
    for mid in members:
        inst = game.combat_manager.get_player_instance(mid)
        if inst is not None:
            if inst.instance_id in instances:
                return True
            instances.add(inst.instance_id)
    return False


def _in_shared_combat(game: Game, entity_a: str, entity_b: str) -> bool:
    """Check if two specific players share the same combat instance."""
    inst_a = game.combat_manager.get_player_instance(entity_a)
    inst_b = game.combat_manager.get_player_instance(entity_b)
    if inst_a is None or inst_b is None:
        return False
    return inst_a.instance_id == inst_b.instance_id


async def _send_party_update(
    game: Game, recipients: list[str], action: str, **extra: object
) -> None:
    """Send a party_update message to a list of entity_ids."""
    msg: dict = {"type": "party_update", "action": action, **extra}
    for mid in recipients:
        await game.connection_manager.send_to_player(mid, msg)


def _get_entity_name(game: Game, entity_id: str) -> str:
    """Get display name for an entity_id, or the entity_id itself."""
    info = game.player_manager.get_session(entity_id)
    if info:
        return info.entity.name
    return entity_id


@requires_auth
async def handle_party(
    websocket: WebSocket, data: dict, *, game: Game,
    entity_id: str, player_info: PlayerSession,
) -> None:
    """Handle the 'party' action — subcommand-based party operations."""
    args_str = data.get("args", "").strip()

    if not args_str:
        # No subcommand — show status
        await _handle_status(websocket, entity_id, game)
        return

    parts = args_str.split()
    subcommand = parts[0].lower()
    sub_args = parts[1:]

    if subcommand == "invite":
        await _handle_invite(websocket, entity_id, sub_args, game)
    elif subcommand == "accept":
        await _handle_accept(websocket, entity_id, game)
    elif subcommand == "reject":
        await _handle_reject(websocket, entity_id, game)
    elif subcommand == "leave":
        await _handle_leave(websocket, entity_id, game)
    elif subcommand == "kick":
        await _handle_kick(websocket, entity_id, sub_args, game)
    elif subcommand == "disband":
        await _handle_disband(websocket, entity_id, game)
    else:
        # Unknown subcommand — route to party chat if in a party
        if game.party_manager.is_in_party(entity_id):
            await handle_party_chat.__wrapped__(
                websocket, {"message": args_str}, game=game,
                entity_id=entity_id, player_info=player_info,
            )
        else:
            await websocket.send_json(
                {"type": "error", "detail": "You are not in a party"}
            )


async def _handle_invite(
    websocket: WebSocket, entity_id: str, sub_args: list[str], game: Game
) -> None:
    """Handle /party invite @PlayerName."""
    if not sub_args:
        await websocket.send_json(
            {"type": "error", "detail": "Usage: /party invite @playername"}
        )
        return

    target_name = sub_args[0].lstrip("@")
    if not target_name:
        await websocket.send_json(
            {"type": "error", "detail": "Usage: /party invite @playername"}
        )
        return

    # Resolve target
    target_id = game.connection_manager.get_entity_id_by_name(target_name)
    if target_id is None:
        await websocket.send_json(
            {"type": "error", "detail": "Player is not online"}
        )
        return

    # Validate target has an active session
    if not game.player_manager.has_session(target_id):
        await websocket.send_json(
            {"type": "error", "detail": "Player is not online"}
        )
        return

    # Self-invite check
    if target_id == entity_id:
        await websocket.send_json(
            {"type": "error", "detail": "Cannot invite yourself"}
        )
        return

    # Target already in a party
    if game.party_manager.is_in_party(target_id):
        await websocket.send_json(
            {
                "type": "error",
                "detail": "Player is already in a party \u2014 they must /party leave first",
            }
        )
        return

    # Target already has a pending invite
    if game.party_manager.has_pending_invite(target_id):
        await websocket.send_json(
            {"type": "error", "detail": "Player already has a pending invite"}
        )
        return

    # Per-target cooldown
    if game.party_manager.check_cooldown(entity_id, target_id):
        await websocket.send_json(
            {"type": "error", "detail": "Please wait before re-inviting this player"}
        )
        return

    # Party full check
    party = game.party_manager.get_party(entity_id)
    if party and len(party.members) >= settings.MAX_PARTY_SIZE:
        await websocket.send_json(
            {"type": "error", "detail": "Party is full"}
        )
        return

    # Cancel existing outgoing invite if any
    old_target = game.party_manager.get_outgoing_invite(entity_id)
    if old_target is not None:
        game.party_manager.cancel_invite(old_target)

    # Resolve display names before storing
    target_display = _get_entity_name(game, target_id)

    # Store invite and schedule timeout
    game.party_manager.create_invite(entity_id, target_id, target_display)

    # Notify target
    inviter_name = _get_entity_name(game, entity_id)
    await game.connection_manager.send_to_player(
        target_id,
        {
            "type": "party_invite",
            "from_player": inviter_name,
            "from_entity_id": entity_id,
        },
    )

    # Confirm to inviter
    await websocket.send_json(
        {
            "type": "party_invite_response",
            "status": "sent",
            "target": target_display,
        }
    )


async def _handle_accept(
    websocket: WebSocket, entity_id: str, game: Game
) -> None:
    """Handle /party accept."""
    inviter_id = game.party_manager.get_pending_invite(entity_id)
    if inviter_id is None:
        await websocket.send_json(
            {"type": "error", "detail": "No pending party invite"}
        )
        return

    # Cancel timeout and remove invite
    game.party_manager.cancel_invite(entity_id)

    # Reject if accepter is already in a party
    if game.party_manager.is_in_party(entity_id):
        await websocket.send_json(
            {"type": "error", "detail": "You are already in a party"}
        )
        return

    # Verify inviter still online
    if game.connection_manager.get_websocket(inviter_id) is None:
        await websocket.send_json(
            {"type": "error", "detail": "Inviter is no longer online"}
        )
        return

    # Create or join party
    inviter_party = game.party_manager.get_party(inviter_id)
    if inviter_party is not None:
        result = game.party_manager.add_member(inviter_party.party_id, entity_id)
    else:
        result = game.party_manager.create_party(inviter_id, entity_id)

    if isinstance(result, str):
        await websocket.send_json({"type": "error", "detail": result})
        return

    # Notify all party members
    party = result
    await _send_party_update(
        game,
        list(party.members),
        "member_joined",
        entity_id=entity_id,
        members=list(party.members),
        leader=party.leader,
    )


async def _handle_reject(
    websocket: WebSocket, entity_id: str, game: Game
) -> None:
    """Handle /party reject."""
    inviter_id = game.party_manager.get_pending_invite(entity_id)
    if inviter_id is None:
        await websocket.send_json(
            {"type": "error", "detail": "No pending party invite"}
        )
        return

    # Cancel and clean up
    game.party_manager.cancel_invite(entity_id)

    # Set cooldown for re-inviting
    game.party_manager.set_cooldown(inviter_id, entity_id)

    # Notify inviter
    rejecter_name = _get_entity_name(game, entity_id)
    await game.connection_manager.send_to_player(
        inviter_id,
        {
            "type": "party_invite_response",
            "status": "rejected",
            "target": rejecter_name,
        },
    )

    # Confirm to rejecter
    await websocket.send_json(
        {"type": "party_invite_response", "status": "rejected"}
    )


async def _handle_leave(
    websocket: WebSocket, entity_id: str, game: Game
) -> None:
    """Handle /party leave."""
    if not game.party_manager.is_in_party(entity_id):
        await websocket.send_json(
            {"type": "error", "detail": "You are not in a party"}
        )
        return

    party, new_leader_id = game.party_manager.remove_member(entity_id)

    if party is not None and party.members:
        update_msg: dict = {
            "type": "party_update",
            "action": "member_left",
            "entity_id": entity_id,
            "members": list(party.members),
            "leader": party.leader,
        }
        if new_leader_id:
            update_msg["new_leader"] = new_leader_id
        for mid in party.members:
            await game.connection_manager.send_to_player(mid, update_msg)

    await websocket.send_json(
        {"type": "party_update", "action": "member_left", "entity_id": entity_id}
    )


async def _handle_kick(
    websocket: WebSocket, entity_id: str, sub_args: list[str], game: Game
) -> None:
    """Handle /party kick @PlayerName."""
    if not game.party_manager.is_leader(entity_id):
        await websocket.send_json(
            {"type": "error", "detail": "Only the party leader can kick members"}
        )
        return

    if not sub_args:
        await websocket.send_json(
            {"type": "error", "detail": "Usage: /party kick @playername"}
        )
        return

    target_name = sub_args[0].lstrip("@")
    if not target_name:
        await websocket.send_json(
            {"type": "error", "detail": "Usage: /party kick @playername"}
        )
        return

    target_id = game.connection_manager.get_entity_id_by_name(target_name)
    if target_id is None:
        await websocket.send_json(
            {"type": "error", "detail": "Player is not online"}
        )
        return

    # Verify target is in the same party
    my_party = game.party_manager.get_party(entity_id)
    target_party = game.party_manager.get_party(target_id)
    if my_party is None or target_party is None or my_party.party_id != target_party.party_id:
        await websocket.send_json(
            {"type": "error", "detail": "Player is not in your party"}
        )
        return

    # Cannot kick self
    if target_id == entity_id:
        await websocket.send_json(
            {"type": "error", "detail": "Cannot kick yourself. Use /party leave"}
        )
        return

    # Shared combat check
    if _in_shared_combat(game, entity_id, target_id):
        await websocket.send_json(
            {"type": "error", "detail": "Cannot kick a player during shared combat"}
        )
        return

    # Remove target from party
    party, new_leader_id = game.party_manager.remove_member(target_id)

    # Set cooldown for re-inviting
    game.party_manager.set_cooldown(entity_id, target_id)

    # Notify remaining members
    if party is not None and party.members:
        await _send_party_update(
            game,
            list(party.members),
            "member_kicked",
            entity_id=target_id,
            members=list(party.members),
            leader=party.leader,
        )

    # Notify kicked player
    await game.connection_manager.send_to_player(
        target_id,
        {
            "type": "party_update",
            "action": "member_kicked",
            "entity_id": target_id,
        },
    )


async def _handle_disband(
    websocket: WebSocket, entity_id: str, game: Game
) -> None:
    """Handle /party disband."""
    if not game.party_manager.is_leader(entity_id):
        await websocket.send_json(
            {"type": "error", "detail": "Only the party leader can disband"}
        )
        return

    party = game.party_manager.get_party(entity_id)
    if party is None:
        await websocket.send_json(
            {"type": "error", "detail": "You are not in a party"}
        )
        return

    # Shared combat check
    if _members_share_combat(game, party.members):
        await websocket.send_json(
            {"type": "error", "detail": "Cannot disband during active party combat"}
        )
        return

    members = game.party_manager.disband(party.party_id)

    # Notify all former members
    await _send_party_update(game, members, "disbanded")


async def _handle_status(
    websocket: WebSocket, entity_id: str, game: Game
) -> None:
    """Handle /party (no subcommand) — show party status or pending invite."""
    party = game.party_manager.get_party(entity_id)

    if party is not None:
        # Show party members with room info
        members_info = []
        for mid in party.members:
            name = _get_entity_name(game, mid)
            room = game.connection_manager.get_room(mid)
            members_info.append({
                "name": name,
                "entity_id": mid,
                "is_leader": mid == party.leader,
                "room": room,
            })

        await websocket.send_json({
            "type": "party_status",
            "party_id": party.party_id,
            "members": members_info,
        })
        return

    # Check for pending invite
    inviter_id = game.party_manager.get_pending_invite(entity_id)
    if inviter_id is not None:
        inviter_name = _get_entity_name(game, inviter_id)
        await websocket.send_json({
            "type": "party_status",
            "pending_invite": True,
            "from_player": inviter_name,
        })
        return

    await websocket.send_json(
        {"type": "error", "detail": "You are not in a party"}
    )


@requires_auth
async def handle_party_chat(
    websocket: WebSocket, data: dict, *, game: Game,
    entity_id: str, player_info: PlayerSession,
) -> None:
    """Handle the 'party_chat' action — send a message to all party members."""
    message = data.get("message", "").strip()
    if not message:
        return  # Ignore empty messages

    if len(message) > settings.MAX_CHAT_MESSAGE_LENGTH:
        await websocket.send_json(
            {
                "type": "error",
                "detail": f"Message too long (max {settings.MAX_CHAT_MESSAGE_LENGTH} characters)",
            }
        )
        return

    party = game.party_manager.get_party(entity_id)
    if party is None:
        await websocket.send_json(
            {"type": "error", "detail": "You are not in a party"}
        )
        return

    sender_name = player_info.entity.name
    msg = {"type": "party_chat", "from": sender_name, "message": message, "format": settings.CHAT_FORMAT}

    for mid in party.members:
        try:
            await game.connection_manager.send_to_player(mid, msg)
        except Exception:
            pass  # Graceful handling of disconnected members
