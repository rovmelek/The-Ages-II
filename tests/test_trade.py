"""Tests for the trade system (Stories 12.1 & 12.2)."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.core.config import settings
from server.items.inventory import Inventory
from server.player.manager import PlayerManager
from server.items.item_def import ItemDef
from server.net.handlers.trade import handle_trade
from server.trade.manager import TradeManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(key: str = "healing_potion", name: str = "Healing Potion",
               tradeable: bool = True) -> ItemDef:
    return ItemDef(item_key=key, name=name, category="consumable",
                   tradeable=tradeable)


def _make_inventory(*items: tuple[ItemDef, int]) -> Inventory:
    inv = Inventory()
    for item_def, qty in items:
        inv.add_item(item_def, qty)
    return inv


def _make_game(
    *,
    players: dict | None = None,
    same_room: bool = True,
) -> MagicMock:
    """Create a mock Game with trade_manager and connection_manager."""
    game = MagicMock()
    game.trade_manager = TradeManager()
    game.connection_manager = MagicMock()
    game.connection_manager.send_to_player = AsyncMock()
    game.player_manager = PlayerManager()
    if players:
        for eid, session in players.items():
            game.player_manager.set_session(eid, session)

    # Default: all players in same room
    if same_room:
        game.connection_manager.get_room.return_value = "town_square"
    return game


def _make_ws(entity_id: str = "player_1") -> tuple[AsyncMock, str]:
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    return ws, entity_id


# ---------------------------------------------------------------------------
# TradeManager unit tests
# ---------------------------------------------------------------------------

class TestTradeManagerInitiate:
    @pytest.mark.asyncio
    async def test_initiate_trade_success(self):
        tm = TradeManager()
        result = tm.initiate_trade("player_1", "player_2")
        assert hasattr(result, "trade_id")
        assert result.state == "request_pending"
        assert result.player_a == "player_1"
        assert result.player_b == "player_2"
        if result.timeout_handle:
            result.timeout_handle.cancel()

    def test_self_trade_rejected(self):
        tm = TradeManager()
        result = tm.initiate_trade("player_1", "player_1")
        assert result == "Cannot trade with yourself"

    @pytest.mark.asyncio
    async def test_already_in_trade(self):
        tm = TradeManager()
        trade = tm.initiate_trade("player_1", "player_2")
        if hasattr(trade, "timeout_handle") and trade.timeout_handle:
            trade.timeout_handle.cancel()
        result = tm.initiate_trade("player_1", "player_3")
        assert result == "You are already in a trade session"

    @pytest.mark.asyncio
    async def test_target_already_in_trade(self):
        tm = TradeManager()
        trade = tm.initiate_trade("player_1", "player_2")
        if hasattr(trade, "timeout_handle") and trade.timeout_handle:
            trade.timeout_handle.cancel()
        result = tm.initiate_trade("player_3", "player_2")
        assert result == "Player is already in a trade session"

    def test_cooldown_enforced(self):
        tm = TradeManager()
        tm._cooldowns["player_1"] = time.time() + 10
        result = tm.initiate_trade("player_1", "player_2")
        assert "Please wait" in result


class TestTradeManagerAcceptReject:
    @pytest.mark.asyncio
    async def test_accept_trade(self):
        tm = TradeManager()
        trade = tm.initiate_trade("player_1", "player_2")
        if trade.timeout_handle:
            trade.timeout_handle.cancel()
        result = tm.accept_trade("player_2")
        assert hasattr(result, "state")
        assert result.state == "negotiating"
        if result.timeout_handle:
            result.timeout_handle.cancel()

    @pytest.mark.asyncio
    async def test_accept_wrong_player(self):
        tm = TradeManager()
        trade = tm.initiate_trade("player_1", "player_2")
        if trade.timeout_handle:
            trade.timeout_handle.cancel()
        result = tm.accept_trade("player_1")
        assert result == "No pending trade request"

    @pytest.mark.asyncio
    async def test_reject_trade(self):
        tm = TradeManager()
        trade = tm.initiate_trade("player_1", "player_2")
        if trade.timeout_handle:
            trade.timeout_handle.cancel()
        result = tm.reject_trade("player_2")
        assert hasattr(result, "state")
        assert result.state == "cancelled"

    def test_reject_no_pending(self):
        tm = TradeManager()
        result = tm.reject_trade("player_1")
        assert result == "No pending trade request"


class TestTradeManagerOffers:
    def _setup_negotiating(self):
        tm = TradeManager()
        trade = tm.initiate_trade("player_1", "player_2")
        if trade.timeout_handle:
            trade.timeout_handle.cancel()
        result = tm.accept_trade("player_2")
        if result.timeout_handle:
            result.timeout_handle.cancel()
        return tm, result

    @pytest.mark.asyncio
    async def test_add_offer(self):
        tm, trade = self._setup_negotiating()
        result = tm.add_offer("player_1", "healing_potion", 2)
        assert hasattr(result, "offers_a")
        assert result.offers_a == {"healing_potion": 2}

    @pytest.mark.asyncio
    async def test_add_offer_resets_ready(self):
        tm, trade = self._setup_negotiating()
        tm.set_ready("player_1")
        assert trade.ready_a is True
        tm.add_offer("player_1", "healing_potion", 1)
        assert trade.ready_a is False
        assert trade.ready_b is False

    @pytest.mark.asyncio
    async def test_remove_offer(self):
        tm, trade = self._setup_negotiating()
        tm.add_offer("player_1", "healing_potion", 2)
        result = tm.remove_offer("player_1", "healing_potion")
        assert hasattr(result, "offers_a")
        assert result.offers_a == {}

    @pytest.mark.asyncio
    async def test_remove_offer_not_found(self):
        tm, trade = self._setup_negotiating()
        result = tm.remove_offer("player_1", "nonexistent")
        assert result == "Item not in your offer"

    @pytest.mark.asyncio
    async def test_max_trade_items_limit(self):
        tm, trade = self._setup_negotiating()
        for i in range(settings.MAX_TRADE_ITEMS):
            tm.add_offer("player_1", f"item_{i}", 1)
        result = tm.add_offer("player_1", "one_more", 1)
        assert "Cannot offer more than" in result

    @pytest.mark.asyncio
    async def test_remove_offer_resets_ready(self):
        tm, trade = self._setup_negotiating()
        tm.add_offer("player_1", "healing_potion", 1)
        tm.set_ready("player_2")
        assert trade.ready_b is True
        tm.remove_offer("player_1", "healing_potion")
        assert trade.ready_b is False


class TestTradeManagerReady:
    def _setup_negotiating(self):
        tm = TradeManager()
        trade = tm.initiate_trade("player_1", "player_2")
        if trade.timeout_handle:
            trade.timeout_handle.cancel()
        result = tm.accept_trade("player_2")
        if result.timeout_handle:
            result.timeout_handle.cancel()
        return tm, result

    @pytest.mark.asyncio
    async def test_one_ready(self):
        tm, trade = self._setup_negotiating()
        result = tm.set_ready("player_1")
        assert result.state == "one_ready"
        assert result.ready_a is True
        assert result.ready_b is False

    @pytest.mark.asyncio
    async def test_both_ready(self):
        tm, trade = self._setup_negotiating()
        tm.set_ready("player_1")
        result = tm.set_ready("player_2")
        assert result.state == "both_ready"
        assert result.ready_a is True
        assert result.ready_b is True


class TestTradeManagerCancel:
    @pytest.mark.asyncio
    async def test_cancel_trade(self):
        tm = TradeManager()
        trade = tm.initiate_trade("player_1", "player_2")
        if trade.timeout_handle:
            trade.timeout_handle.cancel()
        result = tm.cancel_trade("player_1")
        assert hasattr(result, "state")
        assert result.state == "cancelled"
        assert tm.get_trade("player_1") is None
        assert tm.get_trade("player_2") is None

    @pytest.mark.asyncio
    async def test_cancel_trades_for_disconnect(self):
        tm = TradeManager()
        trade = tm.initiate_trade("player_1", "player_2")
        if trade.timeout_handle:
            trade.timeout_handle.cancel()
        result = tm.cancel_trades_for("player_1")
        assert result is not None
        assert result.state == "cancelled"

    def test_cancel_trades_for_no_trade(self):
        tm = TradeManager()
        result = tm.cancel_trades_for("player_1")
        assert result is None


class TestTradeManagerTimeout:
    @pytest.mark.asyncio
    async def test_timeout_notifies_players(self):
        cm = AsyncMock()
        cm.send_to_player = AsyncMock()
        tm = TradeManager(connection_manager=cm)
        trade = tm.initiate_trade("player_1", "player_2")
        if trade.timeout_handle:
            trade.timeout_handle.cancel()
        # Manually trigger timeout
        tm._handle_timeout(trade.trade_id)
        # Allow scheduled tasks to run
        await asyncio.sleep(0)
        assert cm.send_to_player.call_count == 2
        calls = cm.send_to_player.call_args_list
        assert calls[0][0][1]["type"] == "trade_result"
        assert calls[0][0][1]["status"] == "timeout"

    @pytest.mark.asyncio
    async def test_timeout_cleans_up_trade(self):
        cm = AsyncMock()
        cm.send_to_player = AsyncMock()
        tm = TradeManager(connection_manager=cm)
        trade = tm.initiate_trade("player_1", "player_2")
        if trade.timeout_handle:
            trade.timeout_handle.cancel()
        tm._handle_timeout(trade.trade_id)
        await asyncio.sleep(0)
        assert tm.get_trade("player_1") is None
        assert tm.get_trade("player_2") is None


class TestTradeManagerCooldown:
    @pytest.mark.asyncio
    async def test_cooldown_set_after_cancel(self):
        tm = TradeManager()
        trade = tm.initiate_trade("player_1", "player_2")
        if trade.timeout_handle:
            trade.timeout_handle.cancel()
        tm.cancel_trade("player_1")
        assert "player_1" in tm._cooldowns
        assert "player_2" in tm._cooldowns

    def test_cooldown_expires(self):
        tm = TradeManager()
        tm._cooldowns["player_1"] = time.time() - 1
        result = tm._check_cooldown("player_1")
        assert result is None


class TestTradeManagerStatus:
    @pytest.mark.asyncio
    async def test_get_trade_status(self):
        tm = TradeManager()
        trade = tm.initiate_trade("player_1", "player_2")
        if trade.timeout_handle:
            trade.timeout_handle.cancel()
        status = tm.get_trade_status("player_1")
        assert status is not None
        assert status["player_a"] == "player_1"
        assert status["state"] == "request_pending"

    def test_get_trade_status_none(self):
        tm = TradeManager()
        assert tm.get_trade_status("player_1") is None


# ---------------------------------------------------------------------------
# Handler tests
# ---------------------------------------------------------------------------

def _entity(name="TestPlayer", entity_id="player_1", db_id=1, in_combat=False):
    e = MagicMock()
    e.name = name
    e.id = entity_id
    e.player_db_id = db_id
    e.in_combat = in_combat
    return e


class TestTradeHandler:

    @pytest.mark.asyncio
    async def test_not_logged_in(self):
        ws, _ = _make_ws()
        game = _make_game()
        game.connection_manager.get_entity_id.return_value = None
        await handle_trade(ws, {"args": ""}, game=game)
        ws.send_json.assert_called_with({"type": "error", "detail": "Not logged in"})

    @pytest.mark.asyncio
    async def test_no_args_no_trade(self):
        ws, eid = _make_ws()
        game = _make_game()
        game.connection_manager.get_entity_id.return_value = eid
        game.player_manager.set_session(eid, _ps({"entity": _entity(), "room_key": "town_square"}))
        await handle_trade(ws, {"args": ""}, game=game)
        ws.send_json.assert_called_with(
            {"type": "error", "detail": "You are not in a trade session"}
        )

    @pytest.mark.asyncio
    async def test_unknown_subcommand(self):
        ws, eid = _make_ws()
        game = _make_game()
        game.connection_manager.get_entity_id.return_value = eid
        game.player_manager.set_session(eid, _ps({"entity": _entity(), "room_key": "town_square"}))
        await handle_trade(ws, {"args": "foobar"}, game=game)
        ws.send_json.assert_called_with(
            {"type": "error", "detail": "Unknown trade command. Use /help for options"}
        )

    @pytest.mark.asyncio
    async def test_initiate_trade_target_not_online(self):
        ws, eid = _make_ws()
        game = _make_game()
        game.connection_manager.get_entity_id.return_value = eid
        game.connection_manager.get_entity_id_by_name.return_value = None
        game.player_manager.set_session(eid, _ps({"entity": _entity(), "room_key": "town_square"}))
        await handle_trade(ws, {"args": "@nobody"}, game=game)
        ws.send_json.assert_called_with(
            {"type": "error", "detail": "Player 'nobody' is not online"}
        )

    @pytest.mark.asyncio
    async def test_initiate_trade_different_room(self):
        ws, eid = _make_ws()
        game = _make_game(same_room=False)
        game.connection_manager.get_entity_id.return_value = eid
        game.connection_manager.get_entity_id_by_name.return_value = "player_2"
        game.connection_manager.get_room.side_effect = lambda x: "town_square" if x == eid else "dark_cave"
        entity = _entity()
        game.player_manager.set_session(eid, _ps({"entity": entity, "room_key": "town_square"}))
        game.player_manager.set_session("player_2", _ps({"entity": _entity("Other", "player_2", 2), "room_key": "dark_cave"}))
        await handle_trade(ws, {"args": "@Other"}, game=game)
        ws.send_json.assert_called_with(
            {"type": "error", "detail": "Player is not in your room"}
        )

    @pytest.mark.asyncio
    async def test_initiate_trade_in_combat(self):
        ws, eid = _make_ws()
        game = _make_game()
        game.connection_manager.get_entity_id.return_value = eid
        game.connection_manager.get_entity_id_by_name.return_value = "player_2"
        entity = _entity(in_combat=True)
        game.player_manager.set_session(eid, _ps({"entity": entity, "room_key": "town_square"}))
        game.player_manager.set_session("player_2", _ps({"entity": _entity("Other", "player_2", 2), "room_key": "town_square"}))
        await handle_trade(ws, {"args": "@Other"}, game=game)
        ws.send_json.assert_called_with(
            {"type": "error", "detail": "Cannot trade while in combat"}
        )

    @pytest.mark.asyncio
    async def test_initiate_trade_success(self):
        ws, eid = _make_ws()
        game = _make_game()
        game.connection_manager.get_entity_id.return_value = eid
        game.connection_manager.get_entity_id_by_name.return_value = "player_2"
        entity = _entity()
        game.player_manager.set_session(eid, _ps({"entity": entity, "room_key": "town_square"}))
        game.player_manager.set_session("player_2", _ps({"entity": _entity("Other", "player_2", 2), "room_key": "town_square"}))
        await handle_trade(ws, {"args": "@Other"}, game=game)
        # Should send trade_request to target
        game.connection_manager.send_to_player.assert_called()
        call_args = game.connection_manager.send_to_player.call_args_list[0]
        assert call_args[0][0] == "player_2"
        assert call_args[0][1]["type"] == "trade_request"
        # Clean up timer
        trade = game.trade_manager.get_trade(eid)
        if trade and trade.timeout_handle:
            trade.timeout_handle.cancel()

    @pytest.mark.asyncio
    async def test_offer_item_insufficient(self):
        ws, eid = _make_ws()
        potion = _make_item()
        inv = _make_inventory((potion, 1))
        game = _make_game()
        game.connection_manager.get_entity_id.return_value = eid
        entity = _entity()
        game.player_manager.set_session(eid, _ps({"entity": entity, "room_key": "town_square", "inventory": inv}))
        game.player_manager.set_session("player_2", _ps({"entity": _entity("Other", "player_2", 2), "room_key": "town_square"}))

        # Set up a trade session
        game.connection_manager.get_entity_id_by_name.return_value = "player_2"
        await handle_trade(ws, {"args": "@Other"}, game=game)
        trade = game.trade_manager.get_trade(eid)
        if trade and trade.timeout_handle:
            trade.timeout_handle.cancel()
        game.trade_manager.accept_trade("player_2")
        trade = game.trade_manager.get_trade(eid)
        if trade and trade.timeout_handle:
            trade.timeout_handle.cancel()

        # Try to offer more than available
        await handle_trade(ws, {"args": "offer healing_potion 5"}, game=game)
        # Should get error about insufficient quantity
        calls = [c[0][0] for c in ws.send_json.call_args_list]
        last_call = ws.send_json.call_args_list[-1][0][0]
        assert last_call["type"] == "error"
        assert "only have" in last_call["detail"]

    @pytest.mark.asyncio
    async def test_offer_untradeable_item(self):
        ws, eid = _make_ws()
        bound_item = _make_item("soul_gem", "Soul Gem", tradeable=False)
        inv = _make_inventory((bound_item, 3))
        game = _make_game()
        game.connection_manager.get_entity_id.return_value = eid
        entity = _entity()
        game.player_manager.set_session(eid, _ps({"entity": entity, "room_key": "town_square", "inventory": inv}))
        game.player_manager.set_session("player_2", _ps({"entity": _entity("Other", "player_2", 2), "room_key": "town_square"}))

        # Set up trade session
        game.connection_manager.get_entity_id_by_name.return_value = "player_2"
        await handle_trade(ws, {"args": "@Other"}, game=game)
        trade = game.trade_manager.get_trade(eid)
        if trade and trade.timeout_handle:
            trade.timeout_handle.cancel()
        game.trade_manager.accept_trade("player_2")
        trade = game.trade_manager.get_trade(eid)
        if trade and trade.timeout_handle:
            trade.timeout_handle.cancel()

        await handle_trade(ws, {"args": "offer soul_gem 1"}, game=game)
        last_call = ws.send_json.call_args_list[-1][0][0]
        assert last_call["type"] == "error"
        assert "not tradeable" in last_call["detail"]

    @pytest.mark.asyncio
    async def test_cancel_subcommand(self):
        ws, eid = _make_ws()
        game = _make_game()
        game.connection_manager.get_entity_id.return_value = eid
        entity = _entity()
        game.player_manager.set_session(eid, _ps({"entity": entity, "room_key": "town_square"}))
        game.player_manager.set_session("player_2", _ps({"entity": _entity("Other", "player_2", 2), "room_key": "town_square"}))

        game.connection_manager.get_entity_id_by_name.return_value = "player_2"
        await handle_trade(ws, {"args": "@Other"}, game=game)
        trade = game.trade_manager.get_trade(eid)
        if trade and trade.timeout_handle:
            trade.timeout_handle.cancel()

        await handle_trade(ws, {"args": "cancel"}, game=game)
        last_call = ws.send_json.call_args_list[-1][0][0]
        assert last_call["type"] == "trade_result"
        assert last_call["status"] == "cancelled"


# ---------------------------------------------------------------------------
# ConnectionManager name index tests
# ---------------------------------------------------------------------------

class TestConnectionManagerNameIndex:
    def test_name_index_on_connect(self):
        from server.net.connection_manager import ConnectionManager
        cm = ConnectionManager()
        ws = MagicMock()
        cm.connect("player_1", ws, "town_square", name="Alice")
        assert cm.get_entity_id_by_name("Alice") == "player_1"
        assert cm.get_entity_id_by_name("alice") == "player_1"
        assert cm.get_entity_id_by_name("ALICE") == "player_1"

    def test_name_index_cleared_on_disconnect(self):
        from server.net.connection_manager import ConnectionManager
        cm = ConnectionManager()
        ws = MagicMock()
        cm.connect("player_1", ws, "town_square", name="Alice")
        cm.disconnect("player_1")
        assert cm.get_entity_id_by_name("Alice") is None

    def test_name_not_found(self):
        from server.net.connection_manager import ConnectionManager
        cm = ConnectionManager()
        assert cm.get_entity_id_by_name("Nobody") is None

    def test_backward_compatible_connect(self):
        from server.net.connection_manager import ConnectionManager
        cm = ConnectionManager()
        ws = MagicMock()
        # Old callers might not pass name
        cm.connect("player_1", ws, "town_square")
        assert cm.get_entity_id_by_name("anything") is None
        # But entity still connects fine
        assert cm.get_entity_id("player_1") is None  # ws lookup uses id()
        assert cm.get_room("player_1") == "town_square"


# ---------------------------------------------------------------------------
# ItemDef tradeable field tests
# ---------------------------------------------------------------------------

class TestItemDefTradeable:
    def test_default_tradeable_true(self):
        item = ItemDef(item_key="test", name="Test", category="consumable")
        assert item.tradeable is True

    def test_tradeable_false(self):
        item = ItemDef(item_key="test", name="Test", category="consumable", tradeable=False)
        assert item.tradeable is False

    def test_to_dict_includes_tradeable(self):
        item = ItemDef(item_key="test", name="Test", category="consumable", tradeable=False)
        d = item.to_dict()
        assert "tradeable" in d
        assert d["tradeable"] is False


# ---------------------------------------------------------------------------
# Story 12.2: Trade Validation tests
# ---------------------------------------------------------------------------

from server.net.handlers.trade import _execute_trade, _validate_offers


from server.player.session import PlayerSession


def _ps(d: dict) -> PlayerSession:
    """Build a PlayerSession from a dict (test helper)."""
    entity = d["entity"]
    return PlayerSession(
        entity=entity,
        room_key=d["room_key"],
        db_id=d.get("db_id") or getattr(entity, "player_db_id", 0),
        inventory=d.get("inventory"),
        visited_rooms=set(d.get("visited_rooms", [])),
        pending_level_ups=d.get("pending_level_ups", 0),
    )


class TestTradePreValidation:
    """Test pre-validation in _execute_trade (AC #1)."""

    @pytest.mark.asyncio
    async def test_execute_fails_player_offline(self):
        """Trade fails if a player goes offline between ready and execute."""
        game = _make_game()
        # Only player_a is registered — player_b is "offline"
        entity_a = _entity("Alice", "player_1", 1)
        potion = _make_item()
        inv_a = _make_inventory((potion, 5))
        game.player_manager.set_session("player_1", _ps({
            "entity": entity_a, "room_key": "town_square",
            "inventory": inv_a, "db_id": 1,
        }))
        # player_2 is NOT in game.player_manager

        trade = game.trade_manager.initiate_trade("player_1", "player_2")
        trade.timeout_handle.cancel()
        game.trade_manager.accept_trade("player_2")
        t = game.trade_manager.get_trade("player_1")
        if t and t.timeout_handle:
            t.timeout_handle.cancel()

        # Set both ready manually
        t.state = "both_ready"
        t.ready_a = True
        t.ready_b = True

        await _execute_trade(t, game)

        # Should fail — player_b offline
        calls = [c[0] for c in game.connection_manager.send_to_player.call_args_list]
        assert any("no longer online" in str(c) for c in calls)

    @pytest.mark.asyncio
    async def test_execute_fails_different_room(self):
        """Trade fails if players move to different rooms before execution."""
        game = _make_game(same_room=False)
        game.connection_manager.get_room.side_effect = lambda x: (
            "town_square" if x == "player_1" else "dark_cave"
        )
        entity_a = _entity("Alice", "player_1", 1)
        entity_b = _entity("Bob", "player_2", 2)
        potion = _make_item()
        game.player_manager.set_session("player_1", _ps({
            "entity": entity_a, "room_key": "town_square",
            "inventory": _make_inventory((potion, 5)), "db_id": 1,
        }))
        game.player_manager.set_session("player_2", _ps({
            "entity": entity_b, "room_key": "dark_cave",
            "inventory": _make_inventory((potion, 3)), "db_id": 2,
        }))

        trade = game.trade_manager.initiate_trade("player_1", "player_2")
        trade.timeout_handle.cancel()
        game.trade_manager.accept_trade("player_2")
        t = game.trade_manager.get_trade("player_1")
        if t and t.timeout_handle:
            t.timeout_handle.cancel()
        t.state = "both_ready"
        t.ready_a = True
        t.ready_b = True

        await _execute_trade(t, game)

        calls = [c[0] for c in game.connection_manager.send_to_player.call_args_list]
        assert any("same room" in str(c) for c in calls)

    @pytest.mark.asyncio
    async def test_execute_fails_in_combat(self):
        """Trade fails if a player enters combat before execution."""
        game = _make_game()
        entity_a = _entity("Alice", "player_1", 1, in_combat=True)
        entity_b = _entity("Bob", "player_2", 2)
        potion = _make_item()
        game.player_manager.set_session("player_1", _ps({
            "entity": entity_a, "room_key": "town_square",
            "inventory": _make_inventory((potion, 5)), "db_id": 1,
        }))
        game.player_manager.set_session("player_2", _ps({
            "entity": entity_b, "room_key": "town_square",
            "inventory": _make_inventory((potion, 3)), "db_id": 2,
        }))

        trade = game.trade_manager.initiate_trade("player_1", "player_2")
        trade.timeout_handle.cancel()
        game.trade_manager.accept_trade("player_2")
        t = game.trade_manager.get_trade("player_1")
        if t and t.timeout_handle:
            t.timeout_handle.cancel()
        t.state = "both_ready"
        t.ready_a = True
        t.ready_b = True

        await _execute_trade(t, game)

        calls = [c[0] for c in game.connection_manager.send_to_player.call_args_list]
        assert any("in combat" in str(c) for c in calls)

    @pytest.mark.asyncio
    async def test_execute_fails_insufficient_items(self):
        """Trade fails if items were consumed between offer and execute."""
        game = _make_game()
        entity_a = _entity("Alice", "player_1", 1)
        entity_b = _entity("Bob", "player_2", 2)
        potion = _make_item()
        inv_a = _make_inventory((potion, 1))  # only 1 but offer says 5
        game.player_manager.set_session("player_1", _ps({
            "entity": entity_a, "room_key": "town_square",
            "inventory": inv_a, "db_id": 1,
        }))
        game.player_manager.set_session("player_2", _ps({
            "entity": entity_b, "room_key": "town_square",
            "inventory": _make_inventory((potion, 3)), "db_id": 2,
        }))

        trade = game.trade_manager.initiate_trade("player_1", "player_2")
        trade.timeout_handle.cancel()
        game.trade_manager.accept_trade("player_2")
        t = game.trade_manager.get_trade("player_1")
        if t and t.timeout_handle:
            t.timeout_handle.cancel()
        # Manually set an offer of 5, but player only has 1
        t.offers_a = {"healing_potion": 5}
        t.state = "both_ready"
        t.ready_a = True
        t.ready_b = True

        await _execute_trade(t, game)

        # Inventory should be unchanged
        assert inv_a.get_quantity("healing_potion") == 1
        calls = [c[0] for c in game.connection_manager.send_to_player.call_args_list]
        assert any("no longer has" in str(c) for c in calls)


class TestValidateOffers:
    """Test _validate_offers helper."""

    def test_valid_offers(self):
        potion = _make_item()
        inv = _make_inventory((potion, 5))
        result = _validate_offers({"healing_potion": 3}, inv, "Alice")
        assert result is None

    def test_insufficient_quantity(self):
        potion = _make_item()
        inv = _make_inventory((potion, 1))
        result = _validate_offers({"healing_potion": 5}, inv, "Alice")
        assert result is not None
        assert "no longer has" in result

    def test_untradeable_item(self):
        bound = _make_item("soul", "Soul Gem", tradeable=False)
        inv = _make_inventory((bound, 3))
        result = _validate_offers({"soul": 1}, inv, "Alice")
        assert result is not None
        assert "not tradeable" in result

    def test_missing_item(self):
        inv = _make_inventory()  # empty
        result = _validate_offers({"nonexistent": 1}, inv, "Alice")
        assert result is not None


class TestAtomicSwap:
    """Test atomic DB transaction behavior (AC #2, #9)."""

    @pytest.mark.asyncio
    async def test_successful_trade_updates_inventories(self):
        """After successful trade, both in-memory inventories are updated."""
        game = _make_game()
        potion = _make_item()
        essence = _make_item("fire_essence", "Fire Essence")
        inv_a = _make_inventory((potion, 5))
        inv_b = _make_inventory((essence, 3))
        entity_a = _entity("Alice", "player_1", 1)
        entity_b = _entity("Bob", "player_2", 2)
        game.player_manager.set_session("player_1", _ps({
            "entity": entity_a, "room_key": "town_square",
            "inventory": inv_a, "db_id": 1,
        }))
        game.player_manager.set_session("player_2", _ps({
            "entity": entity_b, "room_key": "town_square",
            "inventory": inv_b, "db_id": 2,
        }))

        # Mock session factory for DB persistence
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        game.transaction = MagicMock(return_value=mock_ctx)

        trade = game.trade_manager.initiate_trade("player_1", "player_2")
        trade.timeout_handle.cancel()
        game.trade_manager.accept_trade("player_2")
        t = game.trade_manager.get_trade("player_1")
        if t and t.timeout_handle:
            t.timeout_handle.cancel()
        t.offers_a = {"healing_potion": 2}
        t.offers_b = {"fire_essence": 1}
        t.state = "both_ready"
        t.ready_a = True
        t.ready_b = True

        await _execute_trade(t, game)

        # Verify in-memory inventories updated
        assert inv_a.get_quantity("healing_potion") == 3  # had 5, gave 2
        assert inv_a.get_quantity("fire_essence") == 1  # received 1
        assert inv_b.get_quantity("fire_essence") == 2  # had 3, gave 1
        assert inv_b.get_quantity("healing_potion") == 2  # received 2

    @pytest.mark.asyncio
    async def test_db_failure_preserves_inventories(self):
        """If DB commit fails, in-memory inventories remain unchanged."""
        game = _make_game()
        potion = _make_item()
        essence = _make_item("fire_essence", "Fire Essence")
        inv_a = _make_inventory((potion, 5))
        inv_b = _make_inventory((essence, 3))
        entity_a = _entity("Alice", "player_1", 1)
        entity_b = _entity("Bob", "player_2", 2)
        game.player_manager.set_session("player_1", _ps({
            "entity": entity_a, "room_key": "town_square",
            "inventory": inv_a, "db_id": 1,
        }))
        game.player_manager.set_session("player_2", _ps({
            "entity": entity_b, "room_key": "town_square",
            "inventory": inv_b, "db_id": 2,
        }))

        # Mock session where execute raises to simulate DB failure
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("DB write failed"))
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        game.transaction = MagicMock(return_value=mock_ctx)

        trade = game.trade_manager.initiate_trade("player_1", "player_2")
        trade.timeout_handle.cancel()
        game.trade_manager.accept_trade("player_2")
        t = game.trade_manager.get_trade("player_1")
        if t and t.timeout_handle:
            t.timeout_handle.cancel()
        t.offers_a = {"healing_potion": 2}
        t.offers_b = {"fire_essence": 1}
        t.state = "both_ready"
        t.ready_a = True
        t.ready_b = True

        await _execute_trade(t, game)

        # Inventories MUST be unchanged
        assert inv_a.get_quantity("healing_potion") == 5
        assert inv_a.get_quantity("fire_essence") == 0
        assert inv_b.get_quantity("fire_essence") == 3
        assert inv_b.get_quantity("healing_potion") == 0

        # Should have notified both players of failure
        calls = [c[0] for c in game.connection_manager.send_to_player.call_args_list]
        assert any("server error" in str(c) for c in calls)


class TestSelfTradeByDbId:
    """Test self-trade prevention by player_db_id (AC #3)."""

    @pytest.mark.asyncio
    async def test_self_trade_by_db_id(self):
        """Two different entity_ids with same db_id cannot trade."""
        ws, eid = _make_ws()
        game = _make_game()
        game.connection_manager.get_entity_id.return_value = eid
        game.connection_manager.get_entity_id_by_name.return_value = "player_2"
        entity_a = _entity("Alice", "player_1", db_id=42)
        entity_b = _entity("Alice_alt", "player_2", db_id=42)  # same db_id!
        game.player_manager.set_session("player_1", _ps({
            "entity": entity_a, "room_key": "town_square", "db_id": 42,
        }))
        game.player_manager.set_session("player_2", _ps({
            "entity": entity_b, "room_key": "town_square", "db_id": 42,
        }))
        await handle_trade(ws, {"args": "@Alice_alt"}, game=game)
        last_call = ws.send_json.call_args_list[-1][0][0]
        assert last_call["type"] == "error"
        assert "Cannot trade with yourself" in last_call["detail"]


class TestRoomTransitionCancelsTrade:
    """Test trade cancellation on room transition (AC #5)."""

    @pytest.mark.asyncio
    async def test_room_transition_cancels_trade(self):
        from server.net.handlers.movement import _handle_exit_transition
        game = _make_game()
        game.connection_manager.broadcast_to_room = AsyncMock()
        entity = _entity("Alice", "player_1", 1)
        entity.x = 0
        entity.y = 0
        entity.player_db_id = 1
        entity.stats = {"level": 1}
        player_info = _ps({
            "entity": entity, "room_key": "town_square",
            "inventory": _make_inventory(), "db_id": 1,
            "visited_rooms": ["town_square"],
        })
        game.player_manager.set_session("player_1", player_info)

        # Set up trade
        trade = game.trade_manager.initiate_trade("player_1", "player_2")
        trade.timeout_handle.cancel()

        # Mock room objects
        old_room = MagicMock()
        target_room = MagicMock()
        target_room.get_player_spawn.return_value = (5, 5)
        target_room.is_walkable.return_value = True
        target_room.get_state.return_value = {"tiles": [], "entities": [], "objects": []}
        target_room.name = "Test Room"
        game.room_manager.get_room.return_value = target_room

        # Mock session
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        game.transaction = MagicMock(return_value=mock_ctx)

        ws = AsyncMock()
        ws.send_json = AsyncMock()

        exit_info = {"target_room": "test_room", "entry_x": 5, "entry_y": 5}
        await _handle_exit_transition(
            ws, {}, game, "player_1", entity, player_info,
            old_room, "town_square", exit_info, 0, 0,
        )

        # Trade should be cancelled
        assert game.trade_manager.get_trade("player_1") is None
        # Other player should be notified
        notify_calls = game.connection_manager.send_to_player.call_args_list
        trade_cancelled = [c for c in notify_calls if "left the room" in str(c)]
        assert len(trade_cancelled) > 0


class TestCombatEntryCancelsTrade:
    """Test trade cancellation on combat entry (AC #6)."""

    @pytest.mark.asyncio
    async def test_combat_entry_cancels_trade(self):
        from server.net.handlers.movement import _handle_mob_encounter
        game = _make_game()
        entity = _entity("Alice", "player_1", 1)
        player_info = _ps({
            "entity": entity, "room_key": "town_square",
            "inventory": _make_inventory(), "db_id": 1,
        })
        game.player_manager.set_session("player_1", player_info)

        # Set up trade
        trade = game.trade_manager.initiate_trade("player_1", "player_2")
        trade.timeout_handle.cancel()

        # Mock NPC and room
        npc = MagicMock()
        npc.is_alive = True
        npc.in_combat = False
        npc.stats = {"hp": 50, "max_hp": 50, "attack": 10}
        npc.name = "Goblin"
        npc.npc_key = "goblin"
        npc._lock = asyncio.Lock()
        room = MagicMock()
        room.get_npc.return_value = npc

        # Mock card loading and combat manager
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))
        mock_session.commit = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        game.transaction = MagicMock(return_value=mock_ctx)

        instance = MagicMock()
        instance.get_state.return_value = {"mob": {}, "participants": {}}
        game.combat_manager.create_instance.return_value = instance
        game.combat_manager.start_combat.return_value = instance

        # Party manager — player not in party (solo combat)
        game.party_manager = MagicMock()
        game.party_manager.get_party.return_value = None

        # get_websocket must return AsyncMock for send_json
        game.connection_manager.get_websocket.return_value = AsyncMock()

        ws = AsyncMock()
        ws.send_json = AsyncMock()

        game.npc_templates = {"goblin": {"hit_dice": 1}}
        await _handle_mob_encounter(
            ws, game, "player_1", entity, player_info, room,
            {"entity_id": "npc_1"},
        )

        # Trade should be cancelled
        assert game.trade_manager.get_trade("player_1") is None
        # Other player notified
        notify_calls = game.connection_manager.send_to_player.call_args_list
        combat_cancelled = [c for c in notify_calls if "entered combat" in str(c)]
        assert len(combat_cancelled) > 0
