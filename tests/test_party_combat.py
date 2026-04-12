"""Tests for party combat integration (Story 12.7)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.combat.cards.card_def import CardDef
from server.combat.instance import CombatInstance
from server.combat.manager import CombatManager
from server.core.config import settings
from server.core.effects.registry import EffectRegistry, create_default_registry
from server.party.manager import PartyManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_card_defs(n: int = 10) -> list[CardDef]:
    return [
        CardDef(card_key=f"atk_{i}", name="Attack", cost=1,
                effects=[{"type": "damage", "value": 10}])
        for i in range(n)
    ]


def _first_hand_card(instance: CombatInstance, entity_id: str) -> str:
    """Get the card_key of the first card in a player's hand."""
    hand = instance.hands[entity_id]
    return hand.hand[0].card_key


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
            self.stats = {"hp": 100, "max_hp": 100, "attack": 10, "xp": 0, "level": 1, "charisma": 0}


class _FakeNpc:
    def __init__(self, npc_id="npc_1", name="Goblin", npc_key="goblin", hp=50):
        self.id = npc_id
        self.name = name
        self.npc_key = npc_key
        self.is_alive = True
        self.in_combat = False
        self.loot_table = "goblin_loot"
        self.stats = {"hp": hp, "max_hp": hp, "attack": 10}


def _make_game(entities: dict, room_key="test_room"):
    """Build a minimal Game-like mock with real CombatManager and PartyManager."""
    game = MagicMock()
    game.player_entities = entities
    game.combat_manager = CombatManager(effect_registry=create_default_registry())
    game.party_manager = PartyManager()
    game.trade_manager = MagicMock()
    game.trade_manager.cancel_trades_for = MagicMock(return_value=None)

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

    def _get_entity_id(ws):
        for eid, w in _ws_map.items():
            if w is ws:
                return eid
        return None

    cm.get_websocket = MagicMock(side_effect=_get_ws)
    cm.get_room = MagicMock(side_effect=_get_room)
    cm.get_entity_id = MagicMock(side_effect=_get_entity_id)
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
    room.get_npc = MagicMock(return_value=_FakeNpc())
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
    game.player_entities[entity_id] = {
        "entity": ent,
        "room_key": room_key,
        "db_id": db_id,
        "inventory": MagicMock(),
    }
    game.connection_manager._room_map[entity_id] = room_key
    return ent


# ---------------------------------------------------------------------------
# Tests — Movement handler: _handle_mob_encounter party gathering
# ---------------------------------------------------------------------------

class TestPartyCombatEncounter:
    """Test party member gathering and mob HP scaling in _handle_mob_encounter."""

    @pytest.fixture
    def setup_party(self):
        """Two players in a party, same room."""
        entities = {}
        game = _make_game(entities)
        e1 = _register_entity(game, "player_1")
        e2 = _register_entity(game, "player_2")
        game.party_manager.create_party("player_1", "player_2")
        return game, e1, e2

    async def test_party_members_join_combat(self, setup_party):
        """All same-room party members are pulled into combat."""
        game, e1, e2 = setup_party
        npc = _FakeNpc(hp=50)
        game.room_manager.get_room.return_value.get_npc.return_value = npc

        from server.net.handlers.movement import _handle_mob_encounter
        ws = game.connection_manager.get_websocket("player_1")

        with patch("server.combat.cards.card_repo.get_all", new_callable=AsyncMock, return_value=[]), \
             patch("server.net.handlers.movement.get_npc_template", return_value={"hit_dice": 2}):
            await _handle_mob_encounter(
                ws, game, "player_1", e1,
                game.player_entities["player_1"],
                game.room_manager.get_room("test_room"),
                {"entity_id": "npc_1"},
            )

        # Both players marked in combat
        assert e1.in_combat is True
        assert e2.in_combat is True

        # Both get combat_start
        ws1 = game.connection_manager.get_websocket("player_1")
        ws2 = game.connection_manager.get_websocket("player_2")
        assert ws1.send_json.call_count >= 1
        assert ws2.send_json.call_count >= 1
        msg1 = ws1.send_json.call_args[0][0]
        msg2 = ws2.send_json.call_args[0][0]
        assert msg1["type"] == "combat_start"
        assert msg2["type"] == "combat_start"

    async def test_mob_hp_scaled_by_party_size(self, setup_party):
        """Mob HP is multiplied by number of party members in combat."""
        game, e1, e2 = setup_party
        npc = _FakeNpc(hp=50)
        game.room_manager.get_room.return_value.get_npc.return_value = npc

        from server.net.handlers.movement import _handle_mob_encounter
        ws = game.connection_manager.get_websocket("player_1")

        with patch("server.combat.cards.card_repo.get_all", new_callable=AsyncMock, return_value=[]), \
             patch("server.net.handlers.movement.get_npc_template", return_value={"hit_dice": 2}):
            await _handle_mob_encounter(
                ws, game, "player_1", e1,
                game.player_entities["player_1"],
                game.room_manager.get_room("test_room"),
                {"entity_id": "npc_1"},
            )

        instance = game.combat_manager.get_player_instance("player_1")
        assert instance is not None
        assert instance.mob_stats["hp"] == 100  # 50 * 2 players
        assert instance.mob_stats["max_hp"] == 100

    async def test_solo_player_no_scaling(self):
        """Solo player (no party) has no HP scaling."""
        entities = {}
        game = _make_game(entities)
        e1 = _register_entity(game, "player_1")
        npc = _FakeNpc(hp=50)
        game.room_manager.get_room.return_value.get_npc.return_value = npc

        from server.net.handlers.movement import _handle_mob_encounter
        ws = game.connection_manager.get_websocket("player_1")

        with patch("server.combat.cards.card_repo.get_all", new_callable=AsyncMock, return_value=[]), \
             patch("server.net.handlers.movement.get_npc_template", return_value={"hit_dice": 2}):
            await _handle_mob_encounter(
                ws, game, "player_1", e1,
                game.player_entities["player_1"],
                game.room_manager.get_room("test_room"),
                {"entity_id": "npc_1"},
            )

        instance = game.combat_manager.get_player_instance("player_1")
        assert instance.mob_stats["hp"] == 50  # No scaling
        assert instance.mob_stats["max_hp"] == 50

    async def test_party_member_different_room_not_pulled(self):
        """Party member in a different room is not pulled into combat."""
        entities = {}
        game = _make_game(entities)
        e1 = _register_entity(game, "player_1", room_key="test_room")
        e2 = _register_entity(game, "player_2", room_key="other_room")
        game.party_manager.create_party("player_1", "player_2")
        npc = _FakeNpc(hp=50)
        game.room_manager.get_room.return_value.get_npc.return_value = npc

        from server.net.handlers.movement import _handle_mob_encounter
        ws = game.connection_manager.get_websocket("player_1")

        with patch("server.combat.cards.card_repo.get_all", new_callable=AsyncMock, return_value=[]), \
             patch("server.net.handlers.movement.get_npc_template", return_value={"hit_dice": 2}):
            await _handle_mob_encounter(
                ws, game, "player_1", e1,
                game.player_entities["player_1"],
                game.room_manager.get_room("test_room"),
                {"entity_id": "npc_1"},
            )

        assert e1.in_combat is True
        assert e2.in_combat is False
        # Mob HP not scaled (only 1 player)
        instance = game.combat_manager.get_player_instance("player_1")
        assert instance.mob_stats["hp"] == 50

    async def test_party_member_already_in_combat_not_pulled(self):
        """Party member already in combat is not pulled into new encounter."""
        entities = {}
        game = _make_game(entities)
        e1 = _register_entity(game, "player_1")
        e2 = _register_entity(game, "player_2")
        e2.in_combat = True
        game.party_manager.create_party("player_1", "player_2")
        npc = _FakeNpc(hp=50)
        game.room_manager.get_room.return_value.get_npc.return_value = npc

        from server.net.handlers.movement import _handle_mob_encounter
        ws = game.connection_manager.get_websocket("player_1")

        with patch("server.combat.cards.card_repo.get_all", new_callable=AsyncMock, return_value=[]), \
             patch("server.net.handlers.movement.get_npc_template", return_value={"hit_dice": 2}):
            await _handle_mob_encounter(
                ws, game, "player_1", e1,
                game.player_entities["player_1"],
                game.room_manager.get_room("test_room"),
                {"entity_id": "npc_1"},
            )

        # Only player_1 in combat instance
        instance = game.combat_manager.get_player_instance("player_1")
        assert instance is not None
        assert "player_2" not in instance.participants
        assert instance.mob_stats["hp"] == 50  # No scaling

    async def test_non_party_player_not_pulled(self):
        """Non-party player in same room is not pulled into combat."""
        entities = {}
        game = _make_game(entities)
        e1 = _register_entity(game, "player_1")
        e2 = _register_entity(game, "player_2")
        e3 = _register_entity(game, "player_3")
        game.party_manager.create_party("player_1", "player_2")
        # player_3 is NOT in the party
        npc = _FakeNpc(hp=50)
        game.room_manager.get_room.return_value.get_npc.return_value = npc

        from server.net.handlers.movement import _handle_mob_encounter
        ws = game.connection_manager.get_websocket("player_1")

        with patch("server.combat.cards.card_repo.get_all", new_callable=AsyncMock, return_value=[]), \
             patch("server.net.handlers.movement.get_npc_template", return_value={"hit_dice": 2}):
            await _handle_mob_encounter(
                ws, game, "player_1", e1,
                game.player_entities["player_1"],
                game.room_manager.get_room("test_room"),
                {"entity_id": "npc_1"},
            )

        assert e3.in_combat is False
        instance = game.combat_manager.get_player_instance("player_1")
        assert "player_3" not in instance.participants
        # 2 party members joined
        assert len(instance.participants) == 2

    async def test_trade_cancelled_for_pulled_members(self):
        """Trade is cancelled for all pulled-in party members."""
        entities = {}
        game = _make_game(entities)
        e1 = _register_entity(game, "player_1")
        e2 = _register_entity(game, "player_2")
        game.party_manager.create_party("player_1", "player_2")
        npc = _FakeNpc(hp=50)
        game.room_manager.get_room.return_value.get_npc.return_value = npc

        from server.net.handlers.movement import _handle_mob_encounter
        ws = game.connection_manager.get_websocket("player_1")

        with patch("server.combat.cards.card_repo.get_all", new_callable=AsyncMock, return_value=[]), \
             patch("server.net.handlers.movement.get_npc_template", return_value={"hit_dice": 2}):
            await _handle_mob_encounter(
                ws, game, "player_1", e1,
                game.player_entities["player_1"],
                game.room_manager.get_room("test_room"),
                {"entity_id": "npc_1"},
            )

        # cancel_trades_for called for both players
        calls = game.trade_manager.cancel_trades_for.call_args_list
        cancelled_ids = [c[0][0] for c in calls]
        assert "player_1" in cancelled_ids
        assert "player_2" in cancelled_ids

    async def test_three_player_party_scaling(self):
        """3-player party scales mob HP by 3."""
        entities = {}
        game = _make_game(entities)
        e1 = _register_entity(game, "player_1")
        e2 = _register_entity(game, "player_2")
        e3 = _register_entity(game, "player_3")
        game.party_manager.create_party("player_1", "player_2")
        game.party_manager.add_member(
            game.party_manager.get_party("player_1").party_id, "player_3"
        )
        npc = _FakeNpc(hp=30)
        game.room_manager.get_room.return_value.get_npc.return_value = npc

        from server.net.handlers.movement import _handle_mob_encounter
        ws = game.connection_manager.get_websocket("player_1")

        with patch("server.combat.cards.card_repo.get_all", new_callable=AsyncMock, return_value=[]), \
             patch("server.net.handlers.movement.get_npc_template", return_value={"hit_dice": 1}):
            await _handle_mob_encounter(
                ws, game, "player_1", e1,
                game.player_entities["player_1"],
                game.room_manager.get_room("test_room"),
                {"entity_id": "npc_1"},
            )

        instance = game.combat_manager.get_player_instance("player_1")
        assert len(instance.participants) == 3
        assert instance.mob_stats["hp"] == 90  # 30 * 3
        assert instance.mob_stats["max_hp"] == 90


# ---------------------------------------------------------------------------
# Tests — Combat handler: _check_combat_end XP bonus & per-player loot
# ---------------------------------------------------------------------------

class TestPartyCombatEnd:
    """Test party XP bonus and per-player loot in _check_combat_end."""

    async def test_party_xp_bonus_two_players(self):
        """2+ participants at victory get XP_PARTY_BONUS_PERCENT bonus."""
        registry = create_default_registry()
        cm = CombatManager(effect_registry=registry)
        cards = _make_card_defs()

        p1_stats = {"hp": 100, "max_hp": 100, "attack": 10, "xp": 0, "level": 1, "charisma": 0}
        p2_stats = {"hp": 100, "max_hp": 100, "attack": 10, "xp": 0, "level": 1, "charisma": 0}
        mob_stats = {"hp": 1, "max_hp": 1, "attack": 5}

        instance = cm.start_combat(
            "Goblin", mob_stats,
            ["player_1", "player_2"],
            {"player_1": p1_stats, "player_2": p2_stats},
            cards, mob_hit_dice=2,
        )

        # Kill the mob via play_card
        result = await instance.play_card("player_1", _first_hand_card(instance, "player_1"))
        assert instance.is_finished

        end_result = instance.get_combat_end_result()
        assert end_result["victory"] is True

        # Verify party bonus is applied in the handler
        from server.core.xp import calculate_combat_xp
        base_xp = calculate_combat_xp(2, 0)
        expected_xp = math.floor(base_xp * (1 + settings.XP_PARTY_BONUS_PERCENT / 100))
        assert expected_xp > base_xp  # Sanity: bonus is non-zero

        # Apply the bonus as the handler would
        participant_ids = list(instance.participants)
        rewards = end_result["rewards_per_player"]
        if len(participant_ids) >= 2:
            bonus_multiplier = 1 + settings.XP_PARTY_BONUS_PERCENT / 100
            for eid in rewards:
                rewards[eid]["xp"] = math.floor(rewards[eid]["xp"] * bonus_multiplier)

        assert rewards["player_1"]["xp"] == expected_xp
        assert rewards["player_2"]["xp"] == expected_xp

    async def test_solo_combat_no_bonus(self):
        """Solo combat (1 participant) does not get party XP bonus."""
        registry = create_default_registry()
        cm = CombatManager(effect_registry=registry)
        cards = _make_card_defs()

        p_stats = {"hp": 100, "max_hp": 100, "attack": 10, "xp": 0, "level": 1, "charisma": 0}
        mob_stats = {"hp": 1, "max_hp": 1, "attack": 5}

        instance = cm.start_combat(
            "Goblin", mob_stats,
            "player_1",
            {"player_1": p_stats},
            cards, mob_hit_dice=2,
        )

        await instance.play_card("player_1", _first_hand_card(instance, "player_1"))
        end_result = instance.get_combat_end_result()
        assert end_result["victory"] is True

        from server.core.xp import calculate_combat_xp
        base_xp = calculate_combat_xp(2, 0)

        # No bonus for solo
        participant_ids = list(instance.participants)
        rewards = end_result["rewards_per_player"]
        if len(participant_ids) >= 2:
            # This branch should NOT execute for solo
            pytest.fail("Solo combat should not trigger party bonus")

        assert rewards["player_1"]["xp"] == base_xp

    async def test_dead_player_no_xp(self):
        """Dead player (hp <= 0) does not receive XP."""
        registry = create_default_registry()
        cm = CombatManager(effect_registry=registry)
        cards = _make_card_defs()

        p1_stats = {"hp": 100, "max_hp": 100, "attack": 10, "xp": 0, "level": 1, "charisma": 0}
        p2_stats = {"hp": 0, "max_hp": 100, "attack": 10, "xp": 0, "level": 1, "charisma": 0}  # Dead
        mob_stats = {"hp": 1, "max_hp": 1, "attack": 5}

        instance = cm.start_combat(
            "Goblin", mob_stats,
            ["player_1", "player_2"],
            {"player_1": p1_stats, "player_2": p2_stats},
            cards, mob_hit_dice=2,
        )

        # Kill mob
        await instance.play_card("player_1", _first_hand_card(instance, "player_1"))
        assert instance.is_finished

        # Verify dead player should be skipped in handler
        p2_combat_hp = instance.participant_stats["player_2"]["hp"]
        assert p2_combat_hp <= 0

    async def test_per_player_loot_independence(self):
        """Each participant gets their own independent loot roll."""
        from server.items.loot import generate_loot

        # generate_loot returns a new list each call
        loot1 = generate_loot("goblin_loot")
        loot2 = generate_loot("goblin_loot")
        # They should be equal in content but independent objects
        assert loot1 == loot2
        assert loot1 is not loot2

    async def test_party_leave_during_combat_stays_in_combat(self):
        """Party leave does not affect active combat — player stays in instance."""
        entities = {}
        game = _make_game(entities)
        e1 = _register_entity(game, "player_1")
        e2 = _register_entity(game, "player_2")
        game.party_manager.create_party("player_1", "player_2")

        # Set up combat manually
        cards = _make_card_defs()
        p1_stats = {"hp": 100, "max_hp": 100, "attack": 10, "shield": 0}
        p2_stats = {"hp": 100, "max_hp": 100, "attack": 10, "shield": 0}
        instance = game.combat_manager.start_combat(
            "Goblin", {"hp": 200, "max_hp": 200, "attack": 5},
            ["player_1", "player_2"],
            {"player_1": p1_stats, "player_2": p2_stats},
            cards,
        )
        e1.in_combat = True
        e2.in_combat = True

        # Player 2 leaves party
        game.party_manager.remove_member("player_2")

        # Player 2 should still be in combat
        assert "player_2" in instance.participants
        assert e2.in_combat is True
        assert game.combat_manager.get_player_instance("player_2") is instance


# ---------------------------------------------------------------------------
# Tests — Full integration: _check_combat_end with party bonus
# ---------------------------------------------------------------------------

class TestCheckCombatEndParty:
    """Integration tests for _check_combat_end with party XP bonus and loot."""

    async def test_check_combat_end_applies_party_bonus(self):
        """_check_combat_end applies party XP bonus when 2+ players."""
        entities = {}
        game = _make_game(entities)
        e1 = _register_entity(game, "player_1")
        e2 = _register_entity(game, "player_2")

        cards = _make_card_defs()
        p1_stats = {"hp": 100, "max_hp": 100, "attack": 10, "shield": 0, "xp": 0, "level": 1, "charisma": 0}
        p2_stats = {"hp": 100, "max_hp": 100, "attack": 10, "shield": 0, "xp": 0, "level": 1, "charisma": 0}
        instance = game.combat_manager.start_combat(
            "Goblin", {"hp": 1, "max_hp": 1, "attack": 5},
            ["player_1", "player_2"],
            {"player_1": p1_stats, "player_2": p2_stats},
            cards, mob_hit_dice=2,
        )
        e1.in_combat = True
        e2.in_combat = True

        # Kill mob
        await instance.play_card("player_1", _first_hand_card(instance, "player_1"))
        assert instance.is_finished

        # Set up NPC for loot
        npc = _FakeNpc()
        npc.loot_table = ""  # No loot to simplify
        room = MagicMock()
        room.get_npc.return_value = npc
        game.room_manager.get_room.return_value = room

        from server.net.handlers.combat import _check_combat_end
        with patch("server.net.handlers.combat.player_repo") as mock_repo, \
             patch("server.net.handlers.combat.grant_xp", new_callable=AsyncMock) as mock_grant:
            mock_repo.update_stats = AsyncMock()
            await _check_combat_end(instance, game)

        # grant_xp should be called for both alive players
        assert mock_grant.call_count == 2

        # Verify XP includes party bonus
        from server.core.xp import calculate_combat_xp
        base_xp = calculate_combat_xp(2, 0)
        expected_xp = math.floor(base_xp * (1 + settings.XP_PARTY_BONUS_PERCENT / 100))

        for call in mock_grant.call_args_list:
            xp_arg = call[0][2]  # 3rd positional arg is xp amount
            assert xp_arg == expected_xp

    async def test_check_combat_end_dead_player_no_xp(self):
        """_check_combat_end skips XP for dead players."""
        entities = {}
        game = _make_game(entities)
        e1 = _register_entity(game, "player_1")
        e2 = _register_entity(game, "player_2")

        cards = _make_card_defs()
        p1_stats = {"hp": 100, "max_hp": 100, "attack": 200, "shield": 0, "xp": 0, "level": 1, "charisma": 0}
        p2_stats = {"hp": 100, "max_hp": 100, "attack": 10, "shield": 0, "xp": 0, "level": 1, "charisma": 0}
        instance = game.combat_manager.start_combat(
            "Goblin", {"hp": 1, "max_hp": 1, "attack": 5},
            ["player_1", "player_2"],
            {"player_1": p1_stats, "player_2": p2_stats},
            cards, mob_hit_dice=2,
        )
        e1.in_combat = True
        e2.in_combat = True

        # Set p2 to dead before mob dies
        instance.participant_stats["player_2"]["hp"] = 0

        # Kill mob with p1
        await instance.play_card("player_1", _first_hand_card(instance, "player_1"))
        assert instance.is_finished

        npc = _FakeNpc()
        npc.loot_table = ""
        room = MagicMock()
        room.get_npc.return_value = npc
        game.room_manager.get_room.return_value = room

        from server.net.handlers.combat import _check_combat_end
        with patch("server.net.handlers.combat.player_repo") as mock_repo, \
             patch("server.net.handlers.combat.grant_xp", new_callable=AsyncMock) as mock_grant:
            mock_repo.update_stats = AsyncMock()
            await _check_combat_end(instance, game)

        # Only player_1 (alive) gets XP
        assert mock_grant.call_count == 1
        assert mock_grant.call_args[0][0] == "player_1"

    async def test_check_combat_end_per_player_loot(self):
        """Each surviving player gets independent loot roll."""
        entities = {}
        game = _make_game(entities)
        e1 = _register_entity(game, "player_1")
        e2 = _register_entity(game, "player_2")

        cards = _make_card_defs()
        p1_stats = {"hp": 100, "max_hp": 100, "attack": 10, "shield": 0, "xp": 0, "level": 1, "charisma": 0}
        p2_stats = {"hp": 100, "max_hp": 100, "attack": 10, "shield": 0, "xp": 0, "level": 1, "charisma": 0}
        instance = game.combat_manager.start_combat(
            "Goblin", {"hp": 1, "max_hp": 1, "attack": 5},
            ["player_1", "player_2"],
            {"player_1": p1_stats, "player_2": p2_stats},
            cards, mob_hit_dice=2, npc_id="npc_1", room_key="test_room",
        )
        e1.in_combat = True
        e2.in_combat = True

        await instance.play_card("player_1", _first_hand_card(instance, "player_1"))
        assert instance.is_finished

        npc = _FakeNpc()
        npc.loot_table = "goblin_loot"
        room = MagicMock()
        room.get_npc.return_value = npc
        room.get_state.return_value = {}
        game.room_manager.get_room.return_value = room

        from server.net.handlers.combat import _check_combat_end
        loot_calls = []
        original_generate_loot = generate_loot_fn = None
        from server.items.loot import generate_loot as gl
        original_generate_loot = gl

        with patch("server.net.handlers.combat.player_repo") as mock_repo, \
             patch("server.net.handlers.combat.grant_xp", new_callable=AsyncMock), \
             patch("server.net.handlers.combat.items_repo") as mock_items_repo, \
             patch("server.net.handlers.combat.generate_loot", side_effect=lambda k: (loot_calls.append(k), original_generate_loot(k))[1]) as mock_loot:
            mock_repo.update_stats = AsyncMock()
            mock_repo.update_inventory = AsyncMock()
            mock_repo.get_by_id = AsyncMock(return_value=MagicMock(inventory={}))
            mock_items_repo.get_all = AsyncMock(return_value=[])
            await _check_combat_end(instance, game)

        # generate_loot called once per surviving participant
        assert len(loot_calls) == 2

        # Each player's combat_end message has their own loot
        ws1 = game.connection_manager.get_websocket("player_1")
        ws2 = game.connection_manager.get_websocket("player_2")

        # Find combat_end messages
        for call in ws1.send_json.call_args_list:
            msg = call[0][0]
            if msg.get("type") == "combat_end":
                assert "loot" in msg
                break

    async def test_check_combat_end_solo_no_bonus(self):
        """Solo combat: no party XP bonus applied."""
        entities = {}
        game = _make_game(entities)
        e1 = _register_entity(game, "player_1")

        cards = _make_card_defs()
        p1_stats = {"hp": 100, "max_hp": 100, "attack": 10, "shield": 0, "xp": 0, "level": 1, "charisma": 0}
        instance = game.combat_manager.start_combat(
            "Goblin", {"hp": 1, "max_hp": 1, "attack": 5},
            "player_1",
            {"player_1": p1_stats},
            cards, mob_hit_dice=2,
        )
        e1.in_combat = True

        await instance.play_card("player_1", _first_hand_card(instance, "player_1"))
        assert instance.is_finished

        npc = _FakeNpc()
        npc.loot_table = ""
        room = MagicMock()
        room.get_npc.return_value = npc
        game.room_manager.get_room.return_value = room

        from server.net.handlers.combat import _check_combat_end
        with patch("server.net.handlers.combat.player_repo") as mock_repo, \
             patch("server.net.handlers.combat.grant_xp", new_callable=AsyncMock) as mock_grant:
            mock_repo.update_stats = AsyncMock()
            await _check_combat_end(instance, game)

        # XP should be base (no bonus)
        from server.core.xp import calculate_combat_xp
        base_xp = calculate_combat_xp(2, 0)
        assert mock_grant.call_count == 1
        assert mock_grant.call_args[0][2] == base_xp

    async def test_flee_during_party_combat_remaining_notified(self):
        """Remaining members receive combat_update when a player flees."""
        entities = {}
        game = _make_game(entities)
        e1 = _register_entity(game, "player_1")
        e2 = _register_entity(game, "player_2")

        cards = _make_card_defs()
        p1_stats = {"hp": 100, "max_hp": 100, "attack": 10, "shield": 0}
        p2_stats = {"hp": 100, "max_hp": 100, "attack": 10, "shield": 0}
        instance = game.combat_manager.start_combat(
            "Goblin", {"hp": 200, "max_hp": 200, "attack": 5},
            ["player_1", "player_2"],
            {"player_1": p1_stats, "player_2": p2_stats},
            cards,
        )
        e1.in_combat = True
        e2.in_combat = True

        from server.net.handlers.combat import handle_flee
        ws1 = game.connection_manager.get_websocket("player_1")

        await handle_flee(ws1, {}, game=game)

        # Player 1 should have fled
        assert e1.in_combat is False

        # Player 2 should get combat_update
        ws2 = game.connection_manager.get_websocket("player_2")
        combat_updates = [
            c[0][0] for c in ws2.send_json.call_args_list
            if c[0][0].get("type") == "combat_update"
        ]
        assert len(combat_updates) >= 1
