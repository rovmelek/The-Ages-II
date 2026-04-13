"""Trade service — business logic for trade execution."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from server.player import repo as player_repo

if TYPE_CHECKING:
    from server.app import Game

logger = logging.getLogger(__name__)


def _validate_offers(
    offers: dict[str, int], inventory, label: str
) -> str | None:
    """Pre-validate offered items against live inventory. Returns error or None."""
    for item_key, qty in offers.items():
        available = inventory.get_quantity(item_key)
        if available < qty:
            item_def = inventory.get_item(item_key)
            name = item_def.name if item_def else item_key
            return f"{label} no longer has {qty} of {name} (has {available})"
        item_def = inventory.get_item(item_key)
        if item_def is None:
            return f"{label} no longer has item {item_key}"
        if not item_def.tradeable:
            return f"{item_def.name} is not tradeable"
    return None


async def _fail_trade(trade, game: Game, reason: str) -> None:
    """Cancel trade and notify both players of failure."""
    game.trade_manager.cancel_trade(trade.player_a)
    msg = {"type": "trade_result", "status": "failed", "reason": reason}
    await game.connection_manager.send_to_player(trade.player_a, msg)
    await game.connection_manager.send_to_player(trade.player_b, msg)


async def execute_trade(trade, game: Game) -> None:
    """Execute a validated, atomic trade swap between two players."""
    lock = game.trade_manager.get_trade_lock(trade.trade_id)
    async with lock:
        if trade.state != "both_ready":
            return  # Already executing or completed
        trade.state = "executing"

        # --- Pre-validation (no mutations) ---
        player_a_info = game.player_manager.get_session(trade.player_a)
        player_b_info = game.player_manager.get_session(trade.player_b)

        if not player_a_info or not player_b_info:
            await _fail_trade(trade, game, "Trade failed — a player is no longer online")
            return

        entity_a = player_a_info.entity
        entity_b = player_b_info.entity

        # Same room check
        room_a = game.connection_manager.get_room(trade.player_a)
        room_b = game.connection_manager.get_room(trade.player_b)
        if room_a != room_b:
            await _fail_trade(trade, game, "Trade failed — players are no longer in the same room")
            return

        # Not in combat
        if entity_a.in_combat or entity_b.in_combat:
            await _fail_trade(trade, game, "Trade failed — a player is in combat")
            return

        inv_a = player_a_info.inventory
        inv_b = player_b_info.inventory
        if inv_a is None or inv_b is None:
            await _fail_trade(trade, game, "Trade failed — inventory unavailable")
            return

        # Re-validate all offered items from live inventory
        name_a = entity_a.name
        name_b = entity_b.name
        err = _validate_offers(trade.offers_a, inv_a, name_a)
        if err:
            await _fail_trade(trade, game, f"Trade failed — {err}")
            return
        err = _validate_offers(trade.offers_b, inv_b, name_b)
        if err:
            await _fail_trade(trade, game, f"Trade failed — {err}")
            return

        # --- Compute new inventories without mutating Inventory objects ---
        new_inv_a = dict(inv_a.to_dict())
        new_inv_b = dict(inv_b.to_dict())

        # Transfer A's offers: remove from A, add to B
        for item_key, qty in trade.offers_a.items():
            new_inv_a[item_key] = new_inv_a.get(item_key, 0) - qty
            if new_inv_a[item_key] <= 0:
                del new_inv_a[item_key]
            new_inv_b[item_key] = new_inv_b.get(item_key, 0) + qty

        # Transfer B's offers: remove from B, add to A
        for item_key, qty in trade.offers_b.items():
            new_inv_b[item_key] = new_inv_b.get(item_key, 0) - qty
            if new_inv_b[item_key] <= 0:
                del new_inv_b[item_key]
            new_inv_a[item_key] = new_inv_a.get(item_key, 0) + qty

        # --- Single atomic DB transaction ---
        db_id_a = player_a_info.db_id
        db_id_b = player_b_info.db_id
        try:
            async with game.transaction() as session:
                await player_repo.update_inventory(session, db_id_a, new_inv_a)
                await player_repo.update_inventory(session, db_id_b, new_inv_b)
        except Exception:
            logger.exception("Trade DB commit failed for trade %s", trade.trade_id)
            await _fail_trade(trade, game, "Trade failed — server error, no items moved")
            return

    # --- DB commit succeeded — now apply to in-memory Inventory ---
    for item_key, qty in trade.offers_a.items():
        item_def = inv_a.get_item(item_key)
        inv_a.remove_item(item_key, qty)
        if item_def:
            inv_b.add_item(item_def, qty)

    for item_key, qty in trade.offers_b.items():
        item_def = inv_b.get_item(item_key)
        inv_b.remove_item(item_key, qty)
        if item_def:
            inv_a.add_item(item_def, qty)

    # Complete trade
    game.trade_manager.complete_trade(trade)

    # Notify both players with updated inventory
    await game.connection_manager.send_to_player(
        trade.player_a,
        {
            "type": "trade_result",
            "status": "success",
            "reason": "Trade completed successfully",
            "inventory": inv_a.get_inventory(),
        },
    )
    await game.connection_manager.send_to_player(
        trade.player_b,
        {
            "type": "trade_result",
            "status": "success",
            "reason": "Trade completed successfully",
            "inventory": inv_b.get_inventory(),
        },
    )
