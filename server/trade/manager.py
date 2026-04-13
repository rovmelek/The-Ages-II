"""TradeManager — manages mutual exchange trade sessions."""
from __future__ import annotations

import asyncio
import time
import uuid

from server.core.config import settings
from server.trade.session import Trade, TradeState


class TradeManager:
    """Manages active trade sessions with cooldown tracking.

    Timeout notifications are delivered by scheduling an async coroutine via
    ``loop.create_task`` from the sync ``call_later`` callback.  The manager
    stores a reference to the ``ConnectionManager`` (injected via constructor)
    so the callback can send messages.
    """

    def __init__(self, *, connection_manager=None) -> None:
        self._trades: dict[str, Trade] = {}  # trade_id -> Trade
        self._player_trade: dict[str, str] = {}  # entity_id -> trade_id
        self._cooldowns: dict[str, float] = {}  # entity_id -> cooldown_end timestamp
        self._trade_locks: dict[str, asyncio.Lock] = {}  # trade_id -> Lock
        self._connection_manager = connection_manager

    def get_trade_lock(self, trade_id: str) -> asyncio.Lock:
        """Return the lock for a trade, creating it lazily if needed."""
        if trade_id not in self._trade_locks:
            self._trade_locks[trade_id] = asyncio.Lock()
        return self._trade_locks[trade_id]

    def get_trade(self, entity_id: str) -> Trade | None:
        """Get the active trade for a player, or None."""
        trade_id = self._player_trade.get(entity_id)
        if trade_id is None:
            return None
        return self._trades.get(trade_id)

    def _check_cooldown(self, entity_id: str) -> str | None:
        """Return error message if player is in cooldown, else None."""
        end = self._cooldowns.get(entity_id)
        if end is not None and time.time() < end:
            remaining = int(end - time.time()) + 1
            return f"Please wait {remaining}s before starting a new trade"
        return None

    def _set_cooldown(self, entity_id: str) -> None:
        """Set a trade cooldown for a player."""
        self._cooldowns[entity_id] = time.time() + settings.TRADE_COOLDOWN_SECONDS

    def _cancel_timeout(self, trade: Trade) -> None:
        """Cancel the pending timeout for a trade."""
        if trade.timeout_handle is not None:
            trade.timeout_handle.cancel()
            trade.timeout_handle = None

    def _cleanup_trade(self, trade: Trade) -> None:
        """Remove a trade from internal tracking."""
        self._cancel_timeout(trade)
        self._player_trade.pop(trade.player_a, None)
        self._player_trade.pop(trade.player_b, None)
        self._trades.pop(trade.trade_id, None)
        self._trade_locks.pop(trade.trade_id, None)
        self._set_cooldown(trade.player_a)
        self._set_cooldown(trade.player_b)

    def initiate_trade(self, initiator_id: str, target_id: str) -> Trade | str:
        """Start a trade request. Returns Trade on success, error string on failure."""
        if initiator_id == target_id:
            return "Cannot trade with yourself"

        cooldown_err = self._check_cooldown(initiator_id)
        if cooldown_err:
            return cooldown_err

        if initiator_id in self._player_trade:
            return "You are already in a trade session"

        if target_id in self._player_trade:
            return "Player is already in a trade session"

        trade_id = str(uuid.uuid4())
        trade = Trade(
            trade_id=trade_id,
            player_a=initiator_id,
            player_b=target_id,
            state=TradeState.REQUEST_PENDING,
        )

        # Schedule request timeout
        def _on_timeout() -> None:
            self._handle_timeout(trade_id)

        loop = asyncio.get_running_loop()
        trade.timeout_handle = loop.call_later(
            settings.TRADE_REQUEST_TIMEOUT_SECONDS, _on_timeout
        )

        self._trades[trade_id] = trade
        self._player_trade[initiator_id] = trade_id
        self._player_trade[target_id] = trade_id
        return trade

    def _handle_timeout(self, trade_id: str) -> None:
        """Handle trade timeout (called by sync event loop timer).

        Cleans up the trade and schedules async player notifications.
        """
        trade = self._trades.get(trade_id)
        if trade is None:
            return
        player_a = trade.player_a
        player_b = trade.player_b
        trade.state = TradeState.CANCELLED
        trade.timeout_handle = None
        self._cleanup_trade(trade)

        # Schedule async notification (call_later callback is sync)
        if self._connection_manager is not None:
            loop = asyncio.get_running_loop()
            msg = {
                "type": "trade_result",
                "status": "timeout",
                "reason": "Trade timed out",
            }
            loop.create_task(self._connection_manager.send_to_player(player_a, msg))
            loop.create_task(self._connection_manager.send_to_player(player_b, msg))

    def accept_trade(self, entity_id: str) -> Trade | str:
        """Accept a pending trade request. Returns Trade or error string."""
        trade = self.get_trade(entity_id)
        if trade is None:
            return "No pending trade request"

        if trade.state != TradeState.REQUEST_PENDING:
            return "No pending trade request to accept"

        if trade.player_b != entity_id:
            return "No pending trade request"

        self._cancel_timeout(trade)
        trade.state = TradeState.NEGOTIATING

        # Schedule session timeout
        def _on_timeout() -> None:
            self._handle_timeout(trade.trade_id)

        loop = asyncio.get_running_loop()
        trade.timeout_handle = loop.call_later(
            settings.TRADE_SESSION_TIMEOUT_SECONDS, _on_timeout
        )
        return trade

    def reject_trade(self, entity_id: str) -> Trade | str:
        """Reject a pending trade request. Returns Trade or error string."""
        trade = self.get_trade(entity_id)
        if trade is None:
            return "No pending trade request"

        if trade.state != TradeState.REQUEST_PENDING:
            return "No pending trade request to reject"

        if trade.player_b != entity_id:
            return "No pending trade request"

        self._cancel_timeout(trade)
        trade.state = TradeState.CANCELLED
        self._cleanup_trade(trade)
        return trade

    def add_offer(
        self, entity_id: str, item_key: str, quantity: int
    ) -> Trade | str:
        """Add an item offer. Returns Trade or error string."""
        trade = self.get_trade(entity_id)
        if trade is None:
            return "You are not in a trade session"

        if trade.state not in (TradeState.NEGOTIATING, TradeState.ONE_READY, TradeState.BOTH_READY):
            return "Cannot modify offers in current trade state"

        # Determine which side
        if entity_id == trade.player_a:
            offers = trade.offers_a
        elif entity_id == trade.player_b:
            offers = trade.offers_b
        else:
            return "You are not in this trade"

        # Check MAX_TRADE_ITEMS (count distinct item types)
        current_count = len(offers)
        if item_key not in offers and current_count >= settings.MAX_TRADE_ITEMS:
            return f"Cannot offer more than {settings.MAX_TRADE_ITEMS} different items"

        # Add or increase quantity
        offers[item_key] = offers.get(item_key, 0) + quantity

        # Reset ready flags (bait-and-switch prevention)
        trade.ready_a = False
        trade.ready_b = False
        trade.state = TradeState.NEGOTIATING
        return trade

    def remove_offer(self, entity_id: str, item_key: str) -> Trade | str:
        """Remove an item from offers. Returns Trade or error string."""
        trade = self.get_trade(entity_id)
        if trade is None:
            return "You are not in a trade session"

        if trade.state not in (TradeState.NEGOTIATING, TradeState.ONE_READY, TradeState.BOTH_READY):
            return "Cannot modify offers in current trade state"

        if entity_id == trade.player_a:
            offers = trade.offers_a
        elif entity_id == trade.player_b:
            offers = trade.offers_b
        else:
            return "You are not in this trade"

        if item_key not in offers:
            return "Item not in your offer"

        del offers[item_key]

        # Reset ready flags
        trade.ready_a = False
        trade.ready_b = False
        trade.state = TradeState.NEGOTIATING
        return trade

    def set_ready(self, entity_id: str) -> Trade | str:
        """Mark a player as ready. Returns Trade or error string."""
        trade = self.get_trade(entity_id)
        if trade is None:
            return "You are not in a trade session"

        if trade.state not in (TradeState.NEGOTIATING, TradeState.ONE_READY):
            return "Cannot ready in current trade state"

        if entity_id == trade.player_a:
            trade.ready_a = True
        elif entity_id == trade.player_b:
            trade.ready_b = True
        else:
            return "You are not in this trade"

        if trade.ready_a and trade.ready_b:
            trade.state = TradeState.BOTH_READY
        else:
            trade.state = TradeState.ONE_READY
        return trade

    def cancel_trade(self, entity_id: str) -> Trade | str:
        """Cancel an active trade. Returns Trade or error string."""
        trade = self.get_trade(entity_id)
        if trade is None:
            return "You are not in a trade session"

        trade.state = TradeState.CANCELLED
        self._cleanup_trade(trade)
        return trade

    def cancel_trades_for(self, entity_id: str) -> Trade | None:
        """Cancel any trade involving this player. For disconnect cleanup."""
        trade = self.get_trade(entity_id)
        if trade is None:
            return None
        trade.state = TradeState.CANCELLED
        self._cleanup_trade(trade)
        return trade

    def complete_trade(self, trade: Trade) -> None:
        """Mark a trade as complete and clean up."""
        trade.state = TradeState.COMPLETE
        self._cleanup_trade(trade)

    def get_trade_status(self, entity_id: str) -> dict | None:
        """Get the current trade status for display."""
        trade = self.get_trade(entity_id)
        if trade is None:
            return None
        return {
            "player_a": trade.player_a,
            "player_b": trade.player_b,
            "offers_a": dict(trade.offers_a),
            "offers_b": dict(trade.offers_b),
            "ready_a": trade.ready_a,
            "ready_b": trade.ready_b,
            "state": trade.state,
        }
