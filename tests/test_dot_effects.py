"""Tests for DoT (damage-over-time) effect ticking in CombatInstance."""
from __future__ import annotations

import pytest

from server.combat.instance import CombatInstance
from server.combat.cards.card_def import CardDef


def _make_instance(mob_hp=50, mob_attack=10):
    """Create a CombatInstance with one player and a mob."""
    inst = CombatInstance(
        instance_id="test",
        mob_name="Slime",
        mob_stats={"hp": mob_hp, "max_hp": mob_hp, "attack": mob_attack},
    )
    card = CardDef(card_key="basic", name="Basic", cost=0, effects=[{"type": "damage", "value": 1}])
    inst.add_participant("player_1", {"hp": 100, "max_hp": 100, "attack": 10, "xp": 0}, [card])
    return inst


class TestProcessDotEffects:
    """Tests for _process_dot_effects method."""

    def test_dot_ticks_and_decrements_remaining(self):
        inst = _make_instance()
        inst.mob_stats["active_effects"] = [
            {"type": "dot", "subtype": "poison", "value": 6, "remaining": 3},
        ]

        results = inst._process_dot_effects(inst.mob_stats, "Slime")

        assert len(results) == 1
        assert results[0]["type"] == "dot_tick"
        assert results[0]["subtype"] == "poison"
        assert results[0]["value"] == 6
        assert results[0]["target"] == "Slime"
        assert results[0]["remaining"] == 2
        assert inst.mob_stats["hp"] == 44  # 50 - 6

    def test_dot_removed_when_remaining_zero(self):
        inst = _make_instance()
        inst.mob_stats["active_effects"] = [
            {"type": "dot", "subtype": "poison", "value": 5, "remaining": 1},
        ]

        results = inst._process_dot_effects(inst.mob_stats, "Slime")

        assert len(results) == 1
        assert results[0]["remaining"] == 0
        assert inst.mob_stats["active_effects"] == []

    def test_multiple_dots_tick_independently(self):
        inst = _make_instance(mob_hp=100)
        inst.mob_stats["active_effects"] = [
            {"type": "dot", "subtype": "poison", "value": 4, "remaining": 3},
            {"type": "dot", "subtype": "bleed", "value": 6, "remaining": 2},
        ]

        results = inst._process_dot_effects(inst.mob_stats, "Slime")

        assert len(results) == 2
        assert results[0]["subtype"] == "poison"
        assert results[0]["remaining"] == 2
        assert results[1]["subtype"] == "bleed"
        assert results[1]["remaining"] == 1
        assert inst.mob_stats["hp"] == 90  # 100 - 4 - 6

    def test_dot_can_kill_mob(self):
        inst = _make_instance(mob_hp=5)
        inst.mob_stats["active_effects"] = [
            {"type": "dot", "subtype": "poison", "value": 10, "remaining": 2},
        ]

        results = inst._process_dot_effects(inst.mob_stats, "Slime")

        assert inst.mob_stats["hp"] == 0
        assert inst.is_finished is True

    def test_dot_respects_shield_on_player(self):
        inst = _make_instance()
        player_stats = inst.participant_stats["player_1"]
        player_stats["shield"] = 4
        player_stats["active_effects"] = [
            {"type": "dot", "subtype": "poison", "value": 6, "remaining": 2},
        ]

        results = inst._process_dot_effects(player_stats, "player_1")

        assert len(results) == 1
        assert results[0]["value"] == 2  # 6 - 4 shield
        assert results[0]["shield_absorbed"] == 4
        assert player_stats["hp"] == 98  # 100 - 2
        assert player_stats["shield"] == 0

    def test_no_active_effects_returns_empty(self):
        inst = _make_instance()
        results = inst._process_dot_effects(inst.mob_stats, "Slime")
        assert results == []

    def test_empty_active_effects_returns_empty(self):
        inst = _make_instance()
        inst.mob_stats["active_effects"] = []
        results = inst._process_dot_effects(inst.mob_stats, "Slime")
        assert results == []

    def test_non_dot_effects_preserved(self):
        inst = _make_instance()
        inst.mob_stats["active_effects"] = [
            {"type": "buff", "subtype": "haste", "value": 1, "remaining": 3},
            {"type": "dot", "subtype": "poison", "value": 5, "remaining": 1},
        ]

        inst._process_dot_effects(inst.mob_stats, "Slime")

        # Buff should survive, DoT should be removed (remaining was 1)
        assert len(inst.mob_stats["active_effects"]) == 1
        assert inst.mob_stats["active_effects"][0]["type"] == "buff"


class TestDotIntegrationWithActions:
    """Tests that DoT ticks fire during play_card, pass_turn, use_item."""

    @pytest.mark.asyncio
    async def test_play_card_ticks_dots(self):
        inst = _make_instance(mob_hp=100)
        inst.mob_stats["active_effects"] = [
            {"type": "dot", "subtype": "poison", "value": 6, "remaining": 3},
        ]

        result = await inst.play_card("player_1", "basic")

        assert "dot_ticks" in result
        assert len(result["dot_ticks"]) == 1
        assert result["dot_ticks"][0]["subtype"] == "poison"
        assert result["dot_ticks"][0]["value"] == 6
        # Mob took DoT (6); card effect skipped (no EffectRegistry)
        assert inst.mob_stats["hp"] == 94

    @pytest.mark.asyncio
    async def test_pass_turn_ticks_dots(self):
        inst = _make_instance(mob_hp=100)
        inst.mob_stats["active_effects"] = [
            {"type": "dot", "subtype": "bleed", "value": 4, "remaining": 2},
        ]

        result = await inst.pass_turn("player_1")

        assert "dot_ticks" in result
        assert len(result["dot_ticks"]) == 1
        assert result["dot_ticks"][0]["subtype"] == "bleed"
        assert inst.mob_stats["hp"] == 96  # 100 - 4

    @pytest.mark.asyncio
    async def test_no_dot_ticks_key_when_empty(self):
        inst = _make_instance()

        result = await inst.play_card("player_1", "basic")

        assert "dot_ticks" not in result

    @pytest.mark.asyncio
    async def test_venom_fang_full_lifecycle(self):
        """AC 8: venom_fang (6 poison, 3 turns) deals 18 total over 3 turns."""
        inst = _make_instance(mob_hp=200, mob_attack=0)

        # Simulate venom_fang being applied (as handle_dot would do)
        inst.mob_stats["active_effects"] = [
            {"type": "dot", "subtype": "poison", "value": 6, "remaining": 3},
        ]

        total_dot_damage = 0

        # Turn 1
        result1 = await inst.pass_turn("player_1")
        assert "dot_ticks" in result1
        total_dot_damage += result1["dot_ticks"][0]["value"]
        assert result1["dot_ticks"][0]["remaining"] == 2

        # Turn 2
        result2 = await inst.pass_turn("player_1")
        assert "dot_ticks" in result2
        total_dot_damage += result2["dot_ticks"][0]["value"]
        assert result2["dot_ticks"][0]["remaining"] == 1

        # Turn 3
        result3 = await inst.pass_turn("player_1")
        assert "dot_ticks" in result3
        total_dot_damage += result3["dot_ticks"][0]["value"]
        assert result3["dot_ticks"][0]["remaining"] == 0

        # Effect should be removed
        assert inst.mob_stats.get("active_effects", []) == []

        # Total 18 damage from DoT
        assert total_dot_damage == 18

        # Turn 4 — no more DoT
        result4 = await inst.pass_turn("player_1")
        assert "dot_ticks" not in result4

    @pytest.mark.asyncio
    async def test_use_item_ticks_dots(self):
        from unittest.mock import MagicMock
        inst = _make_instance(mob_hp=100, mob_attack=0)
        inst.mob_stats["active_effects"] = [
            {"type": "dot", "subtype": "poison", "value": 3, "remaining": 2},
        ]
        item_def = MagicMock()
        item_def.item_key = "potion"
        item_def.name = "Potion"
        item_def.effects = []

        result = await inst.use_item("player_1", item_def)

        assert "dot_ticks" in result
        assert result["dot_ticks"][0]["value"] == 3
        assert inst.mob_stats["hp"] == 97

    @pytest.mark.asyncio
    async def test_dot_kills_mob_triggers_combat_end(self):
        """AC 5: DoT killing mob ends combat with victory."""
        inst = _make_instance(mob_hp=3, mob_attack=0)
        inst.mob_stats["active_effects"] = [
            {"type": "dot", "subtype": "poison", "value": 5, "remaining": 2},
        ]

        await inst.pass_turn("player_1")

        assert inst.mob_stats["hp"] == 0
        assert inst.is_finished is True
        end = inst.get_combat_end_result()
        assert end is not None
        assert end["victory"] is True

    @pytest.mark.asyncio
    async def test_dot_kills_mob_skips_card_and_mob_attack(self):
        """When DoT kills mob, card effect and mob attack are skipped."""
        inst = _make_instance(mob_hp=3, mob_attack=50)
        inst.mob_stats["active_effects"] = [
            {"type": "dot", "subtype": "poison", "value": 5, "remaining": 2},
        ]

        result = await inst.play_card("player_1", "basic")

        assert inst.mob_stats["hp"] == 0
        assert "dot_ticks" in result
        # No card was played (no "card" key), no mob attack
        assert "card" not in result
        assert "mob_attack" not in result
        # Player should be unharmed (mob_attack=50 never fired)
        assert inst.participant_stats["player_1"]["hp"] == 100
