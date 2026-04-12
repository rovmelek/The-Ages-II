"""Tests for XP calculation, grant_xp, and combat XP rewards."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.core.xp import calculate_combat_xp, grant_xp
from server.combat.instance import CombatInstance


def _mock_transaction():
    """Create a mock async context manager for game.transaction."""
    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_ctx)
    return mock_factory, mock_session


# ---------------------------------------------------------------------------
# calculate_combat_xp unit tests
# ---------------------------------------------------------------------------

class TestCalculateCombatXP:
    """Tests for the calculate_combat_xp function."""

    def test_quadratic_curve_no_cha(self, monkeypatch):
        """Quadratic: hit_dice=4, CHA=0 -> 4^2 * 25 = 400."""
        from server.core import config
        monkeypatch.setattr(config.settings, "XP_CURVE_TYPE", "quadratic")
        monkeypatch.setattr(config.settings, "XP_CURVE_MULTIPLIER", 25)
        monkeypatch.setattr(config.settings, "XP_CHA_BONUS_PER_POINT", 0.03)
        assert calculate_combat_xp(4, 0) == 400

    def test_linear_curve_no_cha(self, monkeypatch):
        """Linear: hit_dice=4, CHA=0 -> 4 * 25 = 100."""
        from server.core import config
        monkeypatch.setattr(config.settings, "XP_CURVE_TYPE", "linear")
        monkeypatch.setattr(config.settings, "XP_CURVE_MULTIPLIER", 25)
        monkeypatch.setattr(config.settings, "XP_CHA_BONUS_PER_POINT", 0.03)
        assert calculate_combat_xp(4, 0) == 100

    def test_cha_1_bonus(self, monkeypatch):
        """CHA=1: floor(400 * 1.03) = 412."""
        from server.core import config
        monkeypatch.setattr(config.settings, "XP_CURVE_TYPE", "quadratic")
        monkeypatch.setattr(config.settings, "XP_CURVE_MULTIPLIER", 25)
        monkeypatch.setattr(config.settings, "XP_CHA_BONUS_PER_POINT", 0.03)
        assert calculate_combat_xp(4, 1) == 412

    def test_cha_6_bonus(self, monkeypatch):
        """CHA=6: floor(400 * 1.18) = 472."""
        from server.core import config
        monkeypatch.setattr(config.settings, "XP_CURVE_TYPE", "quadratic")
        monkeypatch.setattr(config.settings, "XP_CURVE_MULTIPLIER", 25)
        monkeypatch.setattr(config.settings, "XP_CHA_BONUS_PER_POINT", 0.03)
        assert calculate_combat_xp(4, 6) == 472

    def test_cha_10_bonus(self, monkeypatch):
        """CHA=10: floor(400 * 1.30) = 520."""
        from server.core import config
        monkeypatch.setattr(config.settings, "XP_CURVE_TYPE", "quadratic")
        monkeypatch.setattr(config.settings, "XP_CURVE_MULTIPLIER", 25)
        monkeypatch.setattr(config.settings, "XP_CHA_BONUS_PER_POINT", 0.03)
        assert calculate_combat_xp(4, 10) == 520

    def test_hit_dice_0_gives_zero_xp(self, monkeypatch):
        """Legacy NPC without hit_dice (hit_dice=0): 0 XP regardless of CHA."""
        from server.core import config
        monkeypatch.setattr(config.settings, "XP_CURVE_TYPE", "quadratic")
        monkeypatch.setattr(config.settings, "XP_CURVE_MULTIPLIER", 25)
        monkeypatch.setattr(config.settings, "XP_CHA_BONUS_PER_POINT", 0.03)
        assert calculate_combat_xp(0, 1) == 0

    def test_all_npcs_quadratic_cha_1(self, monkeypatch):
        """Verify expected XP for all NPCs at CHA=1 (quadratic, multiplier=25)."""
        from server.core import config
        monkeypatch.setattr(config.settings, "XP_CURVE_TYPE", "quadratic")
        monkeypatch.setattr(config.settings, "XP_CURVE_MULTIPLIER", 25)
        monkeypatch.setattr(config.settings, "XP_CHA_BONUS_PER_POINT", 0.03)

        expected = {
            2: 103,    # cave_bat
            3: 231,    # slime
            4: 412,    # forest_goblin
            7: 1261,   # cave_troll
            10: 2575,  # forest_dragon
        }
        for hd, expected_xp in expected.items():
            result = calculate_combat_xp(hd, 1)
            assert result == expected_xp, f"hit_dice={hd}: expected {expected_xp}, got {result}"


# ---------------------------------------------------------------------------
# CombatInstance.get_combat_end_result per-player XP tests
# ---------------------------------------------------------------------------

class TestCombatEndPerPlayerXP:
    """Tests for per-player XP in get_combat_end_result."""

    def _make_instance(self, mob_hp=0, mob_hit_dice=4):
        """Create a CombatInstance with mob killed (hp=0) for victory testing."""
        instance = CombatInstance(
            mob_name="Test Mob",
            mob_stats={"hp": mob_hp, "max_hp": 50, "attack": 10,
                       "strength": mob_hit_dice, "dexterity": mob_hit_dice},
            mob_hit_dice=mob_hit_dice,
        )
        return instance

    def test_per_player_xp_different_cha(self, monkeypatch):
        """Two players with different CHA get different XP."""
        from server.core import config
        monkeypatch.setattr(config.settings, "XP_CURVE_TYPE", "quadratic")
        monkeypatch.setattr(config.settings, "XP_CURVE_MULTIPLIER", 25)
        monkeypatch.setattr(config.settings, "XP_CHA_BONUS_PER_POINT", 0.03)

        instance = self._make_instance(mob_hp=0, mob_hit_dice=4)
        from server.combat.cards.card_def import CardDef
        cards = [CardDef(card_key="basic", name="Basic", cost=1, effects=[{"type": "damage", "value": 10}])]

        # Player 1: CHA=1
        instance.add_participant("player_1", {
            "hp": 100, "max_hp": 100, "xp": 0,
            "strength": 1, "dexterity": 1, "constitution": 1,
            "intelligence": 1, "wisdom": 1, "charisma": 1,
        }, cards)
        # Player 2: CHA=6
        instance.add_participant("player_2", {
            "hp": 100, "max_hp": 100, "xp": 0,
            "strength": 1, "dexterity": 1, "constitution": 1,
            "intelligence": 1, "wisdom": 1, "charisma": 6,
        }, cards)

        result = instance.get_combat_end_result()
        assert result is not None
        assert result["victory"] is True
        assert "rewards_per_player" in result

        p1_xp = result["rewards_per_player"]["player_1"]["xp"]
        p2_xp = result["rewards_per_player"]["player_2"]["xp"]
        assert p1_xp == 412   # CHA=1: floor(400 * 1.03)
        assert p2_xp == 472   # CHA=6: floor(400 * 1.18)

    def test_defeat_gives_no_xp(self):
        """Defeat (mob alive, all players dead) gives no XP."""
        instance = self._make_instance(mob_hp=50, mob_hit_dice=4)
        from server.combat.cards.card_def import CardDef
        cards = [CardDef(card_key="basic", name="Basic", cost=1, effects=[{"type": "damage", "value": 10}])]
        instance.add_participant("player_1", {
            "hp": 0, "max_hp": 100, "xp": 0,
            "strength": 1, "dexterity": 1, "constitution": 1,
            "intelligence": 1, "wisdom": 1, "charisma": 5,
        }, cards)

        result = instance.get_combat_end_result()
        assert result is not None
        assert result["victory"] is False
        assert result["rewards_per_player"] == {}

    def test_mob_hit_dice_0_gives_zero_xp(self, monkeypatch):
        """Legacy NPC with hit_dice=0 gives 0 XP on victory."""
        from server.core import config
        monkeypatch.setattr(config.settings, "XP_CURVE_TYPE", "quadratic")
        monkeypatch.setattr(config.settings, "XP_CURVE_MULTIPLIER", 25)
        monkeypatch.setattr(config.settings, "XP_CHA_BONUS_PER_POINT", 0.03)

        instance = self._make_instance(mob_hp=0, mob_hit_dice=0)
        from server.combat.cards.card_def import CardDef
        cards = [CardDef(card_key="basic", name="Basic", cost=1, effects=[{"type": "damage", "value": 10}])]
        instance.add_participant("player_1", {
            "hp": 100, "max_hp": 100, "xp": 0,
            "strength": 1, "dexterity": 1, "constitution": 1,
            "intelligence": 1, "wisdom": 1, "charisma": 5,
        }, cards)

        result = instance.get_combat_end_result()
        assert result["victory"] is True
        assert result["rewards_per_player"]["player_1"]["xp"] == 0


# ---------------------------------------------------------------------------
# grant_xp tests
# ---------------------------------------------------------------------------

class TestGrantXP:
    """Tests for the grant_xp shared function."""

    @pytest.fixture
    def _mock_entity(self):
        entity = MagicMock()
        entity.stats = {"xp": 0, "charisma": 6}
        entity.player_db_id = 1
        return entity

    @pytest.fixture
    def _mock_game(self):
        game = MagicMock()
        factory, _ = _mock_transaction()
        game.transaction = factory
        ws = AsyncMock()
        game.connection_manager.get_websocket.return_value = ws
        game.player_entities = {}
        return game

    async def test_grant_xp_applies_cha_bonus(self, monkeypatch, _mock_entity, _mock_game):
        """CHA=6, amount=50 -> floor(50 * 1.18) = 59."""
        from server.core import config
        monkeypatch.setattr(config.settings, "XP_CHA_BONUS_PER_POINT", 0.03)

        with patch("server.core.xp.player_repo") as mock_repo:
            mock_repo.update_stats = AsyncMock()
            result = await grant_xp("player_1", _mock_entity, 50, "exploration", "test", _mock_game)

        assert result == 59
        assert _mock_entity.stats["xp"] == 59

    async def test_grant_xp_no_cha_bonus(self, monkeypatch, _mock_entity, _mock_game):
        """apply_cha_bonus=False passes amount through directly."""
        with patch("server.core.xp.player_repo") as mock_repo:
            mock_repo.update_stats = AsyncMock()
            result = await grant_xp("player_1", _mock_entity, 100, "combat", "test", _mock_game, apply_cha_bonus=False)

        assert result == 100
        assert _mock_entity.stats["xp"] == 100

    async def test_grant_xp_sends_message(self, monkeypatch, _mock_entity, _mock_game):
        """Sends xp_gained message via WebSocket."""
        from server.core import config
        monkeypatch.setattr(config.settings, "XP_CHA_BONUS_PER_POINT", 0.03)

        with patch("server.core.xp.player_repo") as mock_repo:
            mock_repo.update_stats = AsyncMock()
            await grant_xp("player_1", _mock_entity, 50, "exploration", "Discovered Cave", _mock_game)

        ws = _mock_game.connection_manager.get_websocket.return_value
        ws.send_json.assert_called_once()
        msg = ws.send_json.call_args[0][0]
        assert msg["type"] == "xp_gained"
        assert msg["source"] == "exploration"
        assert msg["detail"] == "Discovered Cave"
        assert msg["amount"] == 59

    async def test_grant_xp_updates_stats(self, _mock_entity, _mock_game):
        """Updates player_entity.stats['xp'] with accumulated XP."""
        _mock_entity.stats["xp"] = 100
        _mock_entity.stats["charisma"] = 0

        with patch("server.core.xp.player_repo") as mock_repo:
            mock_repo.update_stats = AsyncMock()
            await grant_xp("player_1", _mock_entity, 50, "interaction", "test", _mock_game)

        assert _mock_entity.stats["xp"] == 150
