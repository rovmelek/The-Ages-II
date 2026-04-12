"""Tests for concurrency safety (Story 14.6).

Uses asyncio.gather to verify that async locks prevent TOCTOU race
conditions in NPC encounter initiation and trade execution.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.combat.manager import CombatManager
from server.core.effects.registry import create_default_registry
from server.party.manager import PartyManager
from server.player.manager import PlayerManager
from server.player.session import PlayerSession
from server.room.objects.npc import NpcEntity


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeEntity:
    id: str
    name: str
    x: int = 0
    y: int = 0
    player_db_id: int = 1
    in_combat: bool = False
    stats: dict = None

    def __post_init__(self):
        if self.stats is None:
            self.stats = {
                "hp": 100, "max_hp": 100, "attack": 10,
                "xp": 0, "level": 1, "charisma": 0,
            }


def _make_game(entities: dict, room_key="test_room"):
    """Build a minimal Game-like mock with real CombatManager and PartyManager."""
    game = MagicMock()
    game.player_manager = PlayerManager()
    for eid, session in entities.items():
        game.player_manager.set_session(eid, session)
    game.combat_manager = CombatManager(effect_registry=create_default_registry())
    game.party_manager = PartyManager()
    game.trade_manager = MagicMock()
    game.trade_manager.cancel_trades_for = MagicMock(return_value=None)
    game.npc_templates = {"goblin": {"hit_dice": 2}}

    # ConnectionManager mock
    cm = MagicMock()
    _ws_map: dict[str, AsyncMock] = {}
    _room_map: dict[str, str] = {}

    def _get_ws(eid):
        if eid not in _ws_map:
            _ws_map[eid] = AsyncMock()
        return _ws_map[eid]

    def _get_room(eid):
        return _room_map.get(eid, room_key)

    cm.get_websocket = MagicMock(side_effect=_get_ws)
    cm.get_room = MagicMock(side_effect=_get_room)
    cm.send_to_player = AsyncMock()
    cm.broadcast_to_room = AsyncMock()
    cm._room_map = _room_map
    cm._ws_map = _ws_map
    game.connection_manager = cm

    # Session factory mock
    mock_session = MagicMock()
    mock_session.commit = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    game.transaction = MagicMock(return_value=mock_ctx)

    # Room manager mock
    room = MagicMock()
    game.room_manager = MagicMock()
    game.room_manager.get_room = MagicMock(return_value=room)

    # kill_npc and respawn_player
    game.kill_npc = AsyncMock()
    game.respawn_player = AsyncMock()

    return game


def _register_entity(game, entity_id, room_key="test_room", db_id=None):
    """Register a fake entity in the game."""
    if db_id is None:
        db_id = int(entity_id.split("_")[1])
    ent = _FakeEntity(id=entity_id, name=f"Player{db_id}", player_db_id=db_id)
    game.player_manager.set_session(entity_id, _ps({
        "entity": ent,
        "room_key": room_key,
        "db_id": db_id,
        "inventory": MagicMock(),
    }))
    game.connection_manager._room_map[entity_id] = room_key
    return ent


def _make_npc(npc_id="npc_1", name="Goblin", npc_key="goblin", hp=50):
    """Create a real NpcEntity (has _lock field for concurrency testing)."""
    return NpcEntity(
        id=npc_id,
        npc_key=npc_key,
        name=name,
        x=3,
        y=3,
        behavior_type="hostile",
        stats={"hp": hp, "max_hp": hp, "attack": 10},
        loot_table="goblin_loot",
    )


# ---------------------------------------------------------------------------
# NPC Encounter Concurrency Tests
# ---------------------------------------------------------------------------


class TestNpcEncounterConcurrency:
    """Verify that the NPC lock prevents two players from engaging the same NPC."""

    @pytest.mark.asyncio
    async def test_two_players_same_npc_only_one_combat(self):
        """Two concurrent _handle_mob_encounter calls on the same NPC
        should result in exactly one combat instance."""
        entities = {}
        game = _make_game(entities)
        e1 = _register_entity(game, "player_1")
        e2 = _register_entity(game, "player_2")

        npc = _make_npc()
        room = game.room_manager.get_room("test_room")
        room.get_npc = MagicMock(return_value=npc)

        from server.net.handlers.movement import _handle_mob_encounter

        ws1 = game.connection_manager.get_websocket("player_1")
        ws2 = game.connection_manager.get_websocket("player_2")
        mob_enc = {"entity_id": "npc_1"}

        with patch("server.combat.cards.card_repo.get_all", new_callable=AsyncMock, return_value=[]):
            await asyncio.gather(
                _handle_mob_encounter(
                    ws1, game, "player_1", e1,
                    game.player_manager.get_session("player_1"), room, mob_enc,
                ),
                _handle_mob_encounter(
                    ws2, game, "player_2", e2,
                    game.player_manager.get_session("player_2"), room, mob_enc,
                ),
            )

        # Only one combat instance should have been created
        assert len(game.combat_manager._instances) == 1
        assert npc.in_combat is True

        # Only one player should be marked in combat (the one who won the race)
        in_combat_count = sum(1 for eid in ["player_1", "player_2"]
                             if game.player_manager.get_session(eid).entity.in_combat)
        assert in_combat_count == 1

    @pytest.mark.asyncio
    async def test_npc_lock_allows_sequential_access(self):
        """Sequential encounters (not concurrent) should work normally."""
        entities = {}
        game = _make_game(entities)
        e1 = _register_entity(game, "player_1")

        npc = _make_npc()
        room = game.room_manager.get_room("test_room")
        room.get_npc = MagicMock(return_value=npc)

        from server.net.handlers.movement import _handle_mob_encounter

        ws1 = game.connection_manager.get_websocket("player_1")
        mob_enc = {"entity_id": "npc_1"}

        with patch("server.combat.cards.card_repo.get_all", new_callable=AsyncMock, return_value=[]):
            await _handle_mob_encounter(
                ws1, game, "player_1", e1,
                game.player_manager.get_session("player_1"), room, mob_enc,
            )

        assert len(game.combat_manager._instances) == 1
        assert npc.in_combat is True
        assert e1.in_combat is True

    @pytest.mark.asyncio
    async def test_npc_dead_skipped_inside_lock(self):
        """Dead NPC returns early inside lock guard."""
        entities = {}
        game = _make_game(entities)
        e1 = _register_entity(game, "player_1")

        npc = _make_npc()
        npc.is_alive = False
        room = game.room_manager.get_room("test_room")
        room.get_npc = MagicMock(return_value=npc)

        from server.net.handlers.movement import _handle_mob_encounter

        ws1 = game.connection_manager.get_websocket("player_1")
        mob_enc = {"entity_id": "npc_1"}

        await _handle_mob_encounter(
            ws1, game, "player_1", e1,
            game.player_manager.get_session("player_1"), room, mob_enc,
        )

        assert len(game.combat_manager._instances) == 0
        assert npc.in_combat is False

    @pytest.mark.asyncio
    async def test_npc_none_returns_early(self):
        """None NPC (removed from room) returns before lock acquisition."""
        entities = {}
        game = _make_game(entities)
        e1 = _register_entity(game, "player_1")

        room = game.room_manager.get_room("test_room")
        room.get_npc = MagicMock(return_value=None)

        from server.net.handlers.movement import _handle_mob_encounter

        ws1 = game.connection_manager.get_websocket("player_1")
        mob_enc = {"entity_id": "npc_1"}

        await _handle_mob_encounter(
            ws1, game, "player_1", e1,
            game.player_manager.get_session("player_1"), room, mob_enc,
        )

        assert len(game.combat_manager._instances) == 0

    @pytest.mark.asyncio
    async def test_npc_in_combat_reset_on_error(self):
        """If combat setup fails after lock, npc.in_combat is reset to False."""
        entities = {}
        game = _make_game(entities)
        e1 = _register_entity(game, "player_1")

        npc = _make_npc()
        room = game.room_manager.get_room("test_room")
        room.get_npc = MagicMock(return_value=npc)

        from server.net.handlers.movement import _handle_mob_encounter

        ws1 = game.connection_manager.get_websocket("player_1")
        mob_enc = {"entity_id": "npc_1"}

        # Make card_repo.get_all raise to simulate failure after lock
        with patch("server.combat.cards.card_repo.get_all", new_callable=AsyncMock,
                   side_effect=RuntimeError("DB error")):
            with pytest.raises(RuntimeError, match="DB error"):
                await _handle_mob_encounter(
                    ws1, game, "player_1", e1,
                    game.player_manager.get_session("player_1"), room, mob_enc,
                )

        # NPC should be released — in_combat reset to False
        assert npc.in_combat is False


# ---------------------------------------------------------------------------
# Trade Execution Concurrency Tests
# ---------------------------------------------------------------------------


class TestTradeExecutionConcurrency:
    """Verify that the trade lock prevents double-execution of trades."""

    @pytest.mark.asyncio
    async def test_concurrent_execute_trade_only_one_succeeds(self):
        """Two concurrent _execute_trade calls on the same trade should
        result in only one successful execution."""
        from server.trade.manager import Trade, TradeManager

        entities = {}
        game = _make_game(entities)
        e1 = _register_entity(game, "player_1")
        e2 = _register_entity(game, "player_2")

        # Set up real TradeManager with trade lock support
        trade_manager = TradeManager()
        game.trade_manager = trade_manager

        # Create inventories with items
        item_def_a = MagicMock(tradeable=True, name="Health Potion")
        inv_a = MagicMock()
        inv_a.to_dict.return_value = {"health_potion": 3}
        inv_a.get_item.return_value = item_def_a
        inv_a.get_quantity.return_value = 3
        inv_a.remove_item = MagicMock()
        inv_a.add_item = MagicMock()
        inv_a.get_inventory.return_value = [{"key": "health_potion", "qty": 2}]

        item_def_b = MagicMock(tradeable=True, name="Iron Sword")
        inv_b = MagicMock()
        inv_b.to_dict.return_value = {"iron_sword": 1}
        inv_b.get_item.return_value = item_def_b
        inv_b.get_quantity.return_value = 1
        inv_b.remove_item = MagicMock()
        inv_b.add_item = MagicMock()
        inv_b.get_inventory.return_value = [{"key": "iron_sword", "qty": 0}]

        game.player_manager.set_session("player_1", _ps({
            "entity": e1, "room_key": "test_room", "db_id": 1,
            "inventory": inv_a,
        }))
        game.player_manager.set_session("player_2", _ps({
            "entity": e2, "room_key": "test_room", "db_id": 2,
            "inventory": inv_b,
        }))

        # Create a trade in both_ready state
        trade = Trade(
            trade_id="trade_1",
            player_a="player_1",
            player_b="player_2",
            state="both_ready",
            offers_a={"health_potion": 1},
            offers_b={},
            ready_a=True,
            ready_b=True,
        )
        trade_manager._trades[trade.trade_id] = trade
        trade_manager._player_trade["player_1"] = trade.trade_id
        trade_manager._player_trade["player_2"] = trade.trade_id

        from server.net.handlers.trade import _execute_trade

        # Track how many times the DB transaction runs
        db_call_count = 0
        original_transaction = game.transaction

        def counting_transaction():
            nonlocal db_call_count
            db_call_count += 1
            return original_transaction()

        game.transaction = counting_transaction

        await asyncio.gather(
            _execute_trade(trade, game),
            _execute_trade(trade, game),
        )

        # The lock serializes access — the second call sees state="executing"
        # or state changes from the first call, preventing double execution.
        # Only one DB transaction should complete successfully.
        assert db_call_count == 1

    @pytest.mark.asyncio
    async def test_trade_lock_cleanup(self):
        """Trade lock is cleaned up when trade is completed."""
        from server.trade.manager import Trade, TradeManager

        trade_manager = TradeManager()
        trade = Trade(
            trade_id="trade_1",
            player_a="player_1",
            player_b="player_2",
            state="both_ready",
        )
        trade_manager._trades[trade.trade_id] = trade
        trade_manager._player_trade["player_1"] = trade.trade_id
        trade_manager._player_trade["player_2"] = trade.trade_id

        # Create a lock via get_trade_lock
        lock = trade_manager.get_trade_lock("trade_1")
        assert "trade_1" in trade_manager._trade_locks

        # Complete the trade — lock should be cleaned up
        trade_manager.complete_trade(trade)
        assert "trade_1" not in trade_manager._trade_locks
        assert "trade_1" not in trade_manager._trades

    @pytest.mark.asyncio
    async def test_trade_lock_lazy_creation(self):
        """get_trade_lock creates locks lazily and returns the same lock."""
        from server.trade.manager import TradeManager

        trade_manager = TradeManager()
        assert len(trade_manager._trade_locks) == 0

        lock1 = trade_manager.get_trade_lock("trade_1")
        lock2 = trade_manager.get_trade_lock("trade_1")
        assert lock1 is lock2
        assert len(trade_manager._trade_locks) == 1

        lock3 = trade_manager.get_trade_lock("trade_2")
        assert lock3 is not lock1
        assert len(trade_manager._trade_locks) == 2
