"""Trade action handler for WebSocket clients."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import WebSocket
from server.net.auth_middleware import requires_auth
from server.net.schemas import with_request_id
from server.player.session import PlayerSession

if TYPE_CHECKING:
    from server.app import Game

logger = logging.getLogger(__name__)


def _resolve_item_key(inventory, name_or_key: str) -> str | None:
    """Resolve an item name or key to item_key from player inventory.

    Matches by item_key first, then case-insensitive display name.
    """
    # Direct key match
    if inventory.has_item(name_or_key):
        return name_or_key
    # Case-insensitive display name match
    for item_key, entry in inventory._items.items():
        if entry["item_def"].name.lower() == name_or_key.lower():
            return item_key
    return None


async def _send_trade_update(trade, game: Game) -> None:
    """Send trade_update to both players."""
    # Resolve player names for display
    player_a_info = game.player_manager.get_session(trade.player_a)
    player_b_info = game.player_manager.get_session(trade.player_b)
    name_a = player_a_info.entity.name if player_a_info else trade.player_a
    name_b = player_b_info.entity.name if player_b_info else trade.player_b

    msg = {
        "type": "trade_update",
        "player_a": name_a,
        "player_b": name_b,
        "offers_a": dict(trade.offers_a),
        "offers_b": dict(trade.offers_b),
        "ready_a": trade.ready_a,
        "ready_b": trade.ready_b,
        "state": trade.state,
    }
    await game.connection_manager.send_to_player_seq(trade.player_a, msg)
    await game.connection_manager.send_to_player_seq(trade.player_b, msg)


@requires_auth
async def handle_trade(
    websocket: WebSocket, data: dict, *, game: Game,
    entity_id: str, player_info: PlayerSession,
) -> None:
    """Handle the 'trade' action — subcommand-based trade operations."""
    entity = player_info.entity
    args_str = data.get("args", "").strip()

    if not args_str:
        # No subcommand — show status or error
        trade = game.trade_manager.get_trade(entity_id)
        if trade is None:
            await websocket.send_json(
                with_request_id({"type": "error", "detail": "You are not in a trade session"}, data)
            )
            return
        await _send_trade_update(trade, game)
        return

    parts = args_str.split()
    subcommand = parts[0].lower()
    sub_args = parts[1:]

    # Initiate trade: /trade @PlayerName
    if subcommand.startswith("@"):
        target_name = subcommand[1:]  # strip @
        if not target_name:
            await websocket.send_json(
                with_request_id({"type": "error", "detail": "Usage: /trade @playername"}, data)
            )
            return

        target_entity_id = game.connection_manager.get_entity_id_by_name(target_name)
        if target_entity_id is None:
            await websocket.send_json(
                with_request_id({"type": "error", "detail": f"Player '{target_name}' is not online"}, data)
            )
            return

        # Check same room
        my_room = game.connection_manager.get_room(entity_id)
        target_room = game.connection_manager.get_room(target_entity_id)
        if my_room != target_room:
            await websocket.send_json(
                with_request_id({"type": "error", "detail": "Player is not in your room"}, data)
            )
            return

        # Check not in combat
        if entity.in_combat:
            await websocket.send_json(
                with_request_id({"type": "error", "detail": "Cannot trade while in combat"}, data)
            )
            return

        target_info = game.player_manager.get_session(target_entity_id)
        if target_info and target_info.entity.in_combat:
            await websocket.send_json(
                with_request_id({"type": "error", "detail": "Target player is in combat"}, data)
            )
            return

        # Check self-trade — by entity_id AND player_db_id (catches duplicate login edge case)
        my_db_id = player_info.db_id
        target_db_id = target_info.db_id if target_info else None
        if target_entity_id == entity_id or (my_db_id is not None and my_db_id == target_db_id):
            await websocket.send_json(
                with_request_id({"type": "error", "detail": "Cannot trade with yourself"}, data)
            )
            return

        result = game.trade_manager.initiate_trade(entity_id, target_entity_id)
        if isinstance(result, str):
            await websocket.send_json(with_request_id({"type": "error", "detail": result}, data))
            return

        # Notify target
        await game.connection_manager.send_to_player(
            target_entity_id,
            {
                "type": "trade_request",
                "from_player": entity.name,
                "from_entity_id": entity_id,
            },
        )
        await websocket.send_json(
            with_request_id({
                "type": "trade_result",
                "status": "request_sent",
                "reason": f"Trade request sent to {target_name}",
            }, data)
        )
        return

    if subcommand == "accept":
        result = game.trade_manager.accept_trade(entity_id)
        if isinstance(result, str):
            await websocket.send_json(with_request_id({"type": "error", "detail": result}, data))
            return
        await _send_trade_update(result, game)
        return

    if subcommand == "reject":
        trade = game.trade_manager.get_trade(entity_id)
        if trade is None:
            await websocket.send_json(
                with_request_id({"type": "error", "detail": "No pending trade request"}, data)
            )
            return
        other_id = trade.player_a if trade.player_b == entity_id else trade.player_b
        result = game.trade_manager.reject_trade(entity_id)
        if isinstance(result, str):
            await websocket.send_json(with_request_id({"type": "error", "detail": result}, data))
            return
        await websocket.send_json(
            with_request_id({"type": "trade_result", "status": "rejected", "reason": "Trade rejected"}, data)
        )
        await game.connection_manager.send_to_player(
            other_id,
            {
                "type": "trade_result",
                "status": "rejected",
                "reason": f"{entity.name} rejected the trade request",
            },
        )
        return

    if subcommand == "offer":
        if not sub_args:
            await websocket.send_json(
                with_request_id({"type": "error", "detail": "Usage: /trade offer <item> [qty] [item qty ...]"}, data)
            )
            return

        inventory = player_info.inventory
        if inventory is None:
            await websocket.send_json(
                with_request_id({"type": "error", "detail": "No inventory"}, data)
            )
            return

        # Parse item_name [qty] pairs
        i = 0
        items_to_offer: list[tuple[str, int]] = []
        while i < len(sub_args):
            item_input = sub_args[i]
            qty = 1
            # Check if next arg is a number (quantity)
            if i + 1 < len(sub_args):
                try:
                    qty = int(sub_args[i + 1])
                    i += 2
                except ValueError:
                    i += 1
            else:
                i += 1

            if qty <= 0:
                await websocket.send_json(
                    with_request_id({"type": "error", "detail": "Quantity must be positive"}, data)
                )
                return

            item_key = _resolve_item_key(inventory, item_input)
            if item_key is None:
                await websocket.send_json(
                    with_request_id({"type": "error", "detail": f"Item '{item_input}' not found in inventory"}, data)
                )
                return

            item_def = inventory.get_item(item_key)
            if item_def and not item_def.tradeable:
                await websocket.send_json(
                    with_request_id({"type": "error", "detail": f"{item_def.name} is not tradeable"}, data)
                )
                return

            available = inventory.get_quantity(item_key)
            # Account for items already offered in this trade
            trade = game.trade_manager.get_trade(entity_id)
            already_offered = 0
            if trade:
                if entity_id == trade.player_a:
                    already_offered = trade.offers_a.get(item_key, 0)
                else:
                    already_offered = trade.offers_b.get(item_key, 0)

            if available - already_offered < qty:
                name = item_def.name if item_def else item_key
                await websocket.send_json(
                    with_request_id({
                        "type": "error",
                        "detail": f"You only have {available - already_offered} of {name}",
                    }, data)
                )
                return

            items_to_offer.append((item_key, qty))

        # Add all validated items
        for item_key, qty in items_to_offer:
            result = game.trade_manager.add_offer(entity_id, item_key, qty)
            if isinstance(result, str):
                await websocket.send_json(with_request_id({"type": "error", "detail": result}, data))
                return

        trade = game.trade_manager.get_trade(entity_id)
        if trade:
            await _send_trade_update(trade, game)
        return

    if subcommand == "remove":
        if not sub_args:
            await websocket.send_json(
                with_request_id({"type": "error", "detail": "Usage: /trade remove <item>"}, data)
            )
            return

        item_input = sub_args[0]
        inventory = player_info.inventory

        # Resolve item key — check inventory first, then check offers directly
        item_key = None
        if inventory:
            item_key = _resolve_item_key(inventory, item_input)
        if item_key is None:
            # Try matching directly against offered item keys
            trade = game.trade_manager.get_trade(entity_id)
            if trade:
                offers = trade.offers_a if entity_id == trade.player_a else trade.offers_b
                if item_input in offers:
                    item_key = item_input
        if item_key is None:
            await websocket.send_json(
                with_request_id({"type": "error", "detail": f"Item '{item_input}' not found"}, data)
            )
            return

        result = game.trade_manager.remove_offer(entity_id, item_key)
        if isinstance(result, str):
            await websocket.send_json(with_request_id({"type": "error", "detail": result}, data))
            return
        await _send_trade_update(result, game)
        return

    if subcommand == "ready":
        result = game.trade_manager.set_ready(entity_id)
        if isinstance(result, str):
            await websocket.send_json(with_request_id({"type": "error", "detail": result}, data))
            return

        await _send_trade_update(result, game)

        # If both ready, execute trade
        if result.state == "both_ready":
            await _execute_trade(result, game)
        return

    if subcommand == "cancel":
        trade = game.trade_manager.get_trade(entity_id)
        if trade is None:
            await websocket.send_json(
                with_request_id({"type": "error", "detail": "You are not in a trade session"}, data)
            )
            return
        other_id = trade.player_a if entity_id != trade.player_a else trade.player_b
        result = game.trade_manager.cancel_trade(entity_id)
        if isinstance(result, str):
            await websocket.send_json(with_request_id({"type": "error", "detail": result}, data))
            return
        await websocket.send_json(
            with_request_id({"type": "trade_result", "status": "cancelled", "reason": "Trade cancelled"}, data)
        )
        await game.connection_manager.send_to_player(
            other_id,
            {
                "type": "trade_result",
                "status": "cancelled",
                "reason": f"{entity.name} cancelled the trade",
            },
        )
        return

    # Unknown subcommand
    await websocket.send_json(
        with_request_id({"type": "error", "detail": "Unknown trade command. Use /help for options"}, data)
    )


async def _execute_trade(trade, game: Game) -> None:
    """Delegate to trade service for atomic trade execution."""
    from server.trade.service import execute_trade
    await execute_trade(trade, game)
