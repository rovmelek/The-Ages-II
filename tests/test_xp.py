"""Tests for XP calculation, grant_xp, and combat XP rewards."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.player.manager import PlayerManager

from server.core.xp import calculate_combat_xp, grant_xp, apply_xp, notify_xp, XpResult
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
        game.player_manager = PlayerManager()
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


# ---------------------------------------------------------------------------
# apply_xp tests
# ---------------------------------------------------------------------------

class TestApplyXp:
    """Tests for apply_xp — business logic only, no WebSocket messaging."""

    @pytest.fixture
    def _mock_entity(self):
        entity = MagicMock()
        entity.stats = {"xp": 0, "charisma": 6, "level": 1}
        entity.player_db_id = 1
        return entity

    @pytest.fixture
    def _mock_game(self):
        game = MagicMock()
        factory, _ = _mock_transaction()
        game.transaction = factory
        ws = AsyncMock()
        game.connection_manager.get_websocket.return_value = ws
        game.player_manager = PlayerManager()
        return game

    async def test_apply_xp_returns_xp_result(self, monkeypatch, _mock_entity, _mock_game):
        """apply_xp returns an XpResult dataclass with correct fields."""
        from server.core import config
        monkeypatch.setattr(config.settings, "XP_CHA_BONUS_PER_POINT", 0.03)

        with patch("server.core.xp.player_repo") as mock_repo:
            mock_repo.update_stats = AsyncMock()
            result = await apply_xp("player_1", _mock_entity, 50, "exploration", "test cave", _mock_game)

        assert isinstance(result, XpResult)
        assert result.final_xp == 59  # floor(50 * 1.18)
        assert result.source == "exploration"
        assert result.detail == "test cave"
        assert result.new_total_xp == 59
        assert result.level_up_available is False

    async def test_apply_xp_persists_to_db(self, _mock_entity, _mock_game):
        """apply_xp calls player_repo.update_stats."""
        _mock_entity.stats["charisma"] = 0

        with patch("server.core.xp.player_repo") as mock_repo:
            mock_repo.update_stats = AsyncMock()
            await apply_xp("player_1", _mock_entity, 100, "combat", "goblin", _mock_game, apply_cha_bonus=False)
            mock_repo.update_stats.assert_called_once()

    async def test_apply_xp_no_websocket_messages(self, _mock_entity, _mock_game):
        """apply_xp does NOT send any WebSocket messages."""
        _mock_entity.stats["charisma"] = 0

        with patch("server.core.xp.player_repo") as mock_repo:
            mock_repo.update_stats = AsyncMock()
            await apply_xp("player_1", _mock_entity, 100, "combat", "test", _mock_game, apply_cha_bonus=False)

        ws = _mock_game.connection_manager.get_websocket.return_value
        ws.send_json.assert_not_called()

    async def test_apply_xp_with_session(self, _mock_entity, _mock_game):
        """apply_xp uses provided session instead of opening a new transaction."""
        _mock_entity.stats["charisma"] = 0
        mock_session = AsyncMock()

        with patch("server.core.xp.player_repo") as mock_repo:
            mock_repo.update_stats = AsyncMock()
            await apply_xp("player_1", _mock_entity, 50, "combat", "test", _mock_game,
                           apply_cha_bonus=False, session=mock_session)
            mock_repo.update_stats.assert_called_once_with(mock_session, 1, _mock_entity.stats)

    async def test_apply_xp_level_up_detection(self, monkeypatch, _mock_entity, _mock_game):
        """apply_xp detects level-up threshold and returns level_up_available=True."""
        from server.core import config
        monkeypatch.setattr(config.settings, "XP_LEVEL_THRESHOLD_MULTIPLIER", 100)
        monkeypatch.setattr(config.settings, "XP_CHA_BONUS_PER_POINT", 0.0)

        # Register player session so level-up detection can find it
        from server.player.session import PlayerSession
        ps = PlayerSession(
            entity=_mock_entity,
            room_key="town_square",
            db_id=1,
        )
        _mock_game.player_manager.set_session("player_1", ps)

        with patch("server.core.xp.player_repo") as mock_repo:
            mock_repo.update_stats = AsyncMock()
            result = await apply_xp("player_1", _mock_entity, 200, "combat", "boss", _mock_game, apply_cha_bonus=False)

        assert result.level_up_available is True
        assert result.new_level == 2


# ---------------------------------------------------------------------------
# notify_xp tests
# ---------------------------------------------------------------------------

class TestNotifyXp:
    """Tests for notify_xp — WebSocket messaging only."""

    @pytest.fixture
    def _mock_entity(self):
        entity = MagicMock()
        entity.stats = {"xp": 200, "level": 1}
        return entity

    @pytest.fixture
    def _mock_game(self):
        game = MagicMock()
        ws = AsyncMock()
        game.connection_manager.get_websocket.return_value = ws
        return game

    async def test_notify_xp_sends_xp_gained(self, _mock_entity, _mock_game):
        """notify_xp sends xp_gained message with XpResult fields."""
        result = XpResult(final_xp=59, source="exploration", detail="cave",
                          new_total_xp=59, level_up_available=False)

        await notify_xp("player_1", result, _mock_entity, _mock_game)

        ws = _mock_game.connection_manager.get_websocket.return_value
        ws.send_json.assert_called_once()
        msg = ws.send_json.call_args[0][0]
        assert msg["type"] == "xp_gained"
        assert msg["amount"] == 59
        assert msg["source"] == "exploration"
        assert msg["detail"] == "cave"
        assert msg["new_total_xp"] == 59

    async def test_notify_xp_calls_level_up_when_available(self, _mock_entity, _mock_game):
        """notify_xp calls send_level_up_available when level_up_available is True."""
        result = XpResult(final_xp=200, source="combat", detail="boss",
                          new_total_xp=200, level_up_available=True, new_level=2)

        with patch("server.core.xp.send_level_up_available", new_callable=AsyncMock) as mock_lu:
            await notify_xp("player_1", result, _mock_entity, _mock_game)
            mock_lu.assert_called_once_with("player_1", _mock_entity, _mock_game)

    async def test_notify_xp_no_level_up_when_not_available(self, _mock_entity, _mock_game):
        """notify_xp does NOT call send_level_up_available when level_up_available is False."""
        result = XpResult(final_xp=50, source="exploration", detail="room",
                          new_total_xp=50, level_up_available=False)

        with patch("server.core.xp.send_level_up_available", new_callable=AsyncMock) as mock_lu:
            await notify_xp("player_1", result, _mock_entity, _mock_game)
            mock_lu.assert_not_called()

    async def test_notify_xp_no_websocket_no_crash(self, _mock_entity, _mock_game):
        """notify_xp handles missing WebSocket gracefully."""
        _mock_game.connection_manager.get_websocket.return_value = None
        result = XpResult(final_xp=50, source="exploration", detail="room",
                          new_total_xp=50, level_up_available=False)

        await notify_xp("player_1", result, _mock_entity, _mock_game)  # should not raise
