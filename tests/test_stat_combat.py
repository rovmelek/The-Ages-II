"""Tests for stat-to-combat integration (Story 11.2).

Verifies that STR, INT, WIS, DEX affect damage, healing, and damage reduction.
"""
from __future__ import annotations

import pytest

from server.combat.cards.card_def import CardDef
from server.combat.instance import CombatInstance
from server.core.effects import create_default_registry


def _registry():
    return create_default_registry()


def _make_mob_stats(hp=100, attack=10, strength=0, dexterity=0, intelligence=0, wisdom=0):
    return {"hp": hp, "max_hp": hp, "attack": attack,
            "strength": strength, "dexterity": dexterity,
            "intelligence": intelligence, "wisdom": wisdom}


def _make_player_stats(hp=100, max_hp=100, strength=0, dexterity=0, intelligence=0, wisdom=0):
    return {"hp": hp, "max_hp": max_hp, "attack": 10, "shield": 0,
            "strength": strength, "dexterity": dexterity,
            "intelligence": intelligence, "wisdom": wisdom}


def _make_instance(cards, mob_stats=None, player_stats=None):
    """Two-player instance so P1's action doesn't trigger cycle-end mob attack."""
    instance = CombatInstance(
        instance_id="test",
        mob_name="Goblin",
        mob_stats=mob_stats or _make_mob_stats(),
        effect_registry=_registry(),
    )
    ps = player_stats or _make_player_stats()
    instance.add_participant("p1", dict(ps), cards)
    instance.add_participant("p2", dict(ps), cards)
    return instance


def _physical_cards(value=12, n=10):
    return [
        CardDef(card_key=f"phys_{i}", name=f"Slash {i}", cost=1,
                effects=[{"type": "damage", "subtype": "physical", "value": value}])
        for i in range(n)
    ]


def _fire_cards(value=20, n=10):
    return [
        CardDef(card_key=f"fire_{i}", name=f"Fire Bolt {i}", cost=1,
                effects=[{"type": "damage", "subtype": "fire", "value": value}])
        for i in range(n)
    ]


def _ice_cards(value=15, n=10):
    return [
        CardDef(card_key=f"ice_{i}", name=f"Ice Shard {i}", cost=1,
                effects=[{"type": "damage", "subtype": "ice", "value": value}])
        for i in range(n)
    ]


def _arcane_cards(value=10, n=10):
    return [
        CardDef(card_key=f"arcane_{i}", name=f"Arcane Surge {i}", cost=1,
                effects=[{"type": "damage", "subtype": "arcane", "value": value}])
        for i in range(n)
    ]


def _heal_cards(value=15, n=10):
    return [
        CardDef(card_key=f"heal_{i}", name=f"Heal {i}", cost=1,
                effects=[{"type": "heal", "value": value}])
        for i in range(n)
    ]


def _shield_cards(value=12, n=10):
    return [
        CardDef(card_key=f"shield_{i}", name=f"Shield {i}", cost=1,
                effects=[{"type": "shield", "value": value}])
        for i in range(n)
    ]


def _dot_cards(value=6, duration=3, n=10):
    return [
        CardDef(card_key=f"dot_{i}", name=f"Poison {i}", cost=1,
                effects=[{"type": "dot", "subtype": "poison", "value": value, "duration": duration}])
        for i in range(n)
    ]


# --- STR scales physical damage ---


@pytest.mark.asyncio
async def test_str_bonus_on_physical_damage():
    """Slash base=12, STR=6 → 12+6=18 raw damage."""
    instance = _make_instance(
        _physical_cards(value=12),
        mob_stats=_make_mob_stats(hp=100),
        player_stats=_make_player_stats(strength=6),
    )
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    assert instance.mob_stats["hp"] == 82  # 100 - 18
    assert result["effect_results"][0]["value"] == 18


@pytest.mark.asyncio
async def test_str_does_not_apply_to_fire_damage():
    """Fire Bolt base=20, STR=6 → should still deal 20 (STR doesn't affect fire)."""
    instance = _make_instance(
        _fire_cards(value=20),
        mob_stats=_make_mob_stats(hp=100),
        player_stats=_make_player_stats(strength=6, intelligence=0),
    )
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    assert instance.mob_stats["hp"] == 80  # 100 - 20
    assert result["effect_results"][0]["value"] == 20


# --- INT scales elemental/arcane damage ---


@pytest.mark.asyncio
async def test_int_bonus_on_fire_damage():
    """Fire Bolt base=20, INT=4 → 20+4=24 raw damage."""
    instance = _make_instance(
        _fire_cards(value=20),
        mob_stats=_make_mob_stats(hp=100),
        player_stats=_make_player_stats(intelligence=4),
    )
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    assert instance.mob_stats["hp"] == 76  # 100 - 24
    assert result["effect_results"][0]["value"] == 24


@pytest.mark.asyncio
async def test_int_bonus_on_ice_damage():
    """Ice Shard base=15, INT=4 → 15+4=19."""
    instance = _make_instance(
        _ice_cards(value=15),
        mob_stats=_make_mob_stats(hp=100),
        player_stats=_make_player_stats(intelligence=4),
    )
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    assert instance.mob_stats["hp"] == 81  # 100 - 19


@pytest.mark.asyncio
async def test_int_bonus_on_arcane_damage():
    """Arcane Surge base=10, INT=4 → 10+4=14."""
    instance = _make_instance(
        _arcane_cards(value=10),
        mob_stats=_make_mob_stats(hp=100),
        player_stats=_make_player_stats(intelligence=4),
    )
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    assert instance.mob_stats["hp"] == 86  # 100 - 14


@pytest.mark.asyncio
async def test_int_does_not_apply_to_physical_damage():
    """Slash base=12, INT=6 → should still deal 12 (INT doesn't affect physical)."""
    instance = _make_instance(
        _physical_cards(value=12),
        mob_stats=_make_mob_stats(hp=100),
        player_stats=_make_player_stats(intelligence=6, strength=0),
    )
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    assert instance.mob_stats["hp"] == 88  # 100 - 12
    assert result["effect_results"][0]["value"] == 12


# --- WIS scales healing ---


@pytest.mark.asyncio
async def test_wis_bonus_on_heal():
    """Heal Light base=15, WIS=3 → 15+3=18 healed."""
    instance = _make_instance(
        _heal_cards(value=15),
        mob_stats=_make_mob_stats(hp=100),
        player_stats=_make_player_stats(hp=70, max_hp=100, wisdom=3),
    )
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    assert instance.participant_stats["p1"]["hp"] == 88  # 70 + 18
    assert result["effect_results"][0]["value"] == 18


@pytest.mark.asyncio
async def test_wis_heal_capped_at_max_hp():
    """Heal with WIS bonus still capped at max_hp."""
    instance = _make_instance(
        _heal_cards(value=15),
        mob_stats=_make_mob_stats(hp=100),
        player_stats=_make_player_stats(hp=95, max_hp=100, wisdom=10),
    )
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    assert instance.participant_stats["p1"]["hp"] == 100  # capped
    assert result["effect_results"][0]["value"] == 5  # only healed 5


# --- DEX reduces incoming damage ---


@pytest.mark.asyncio
async def test_dex_reduces_damage_after_shield():
    """Physical 12, mob DEX=4 → raw 12, shield 0, post_shield=12, DEX reduces by 4 → actual=8."""
    instance = _make_instance(
        _physical_cards(value=12),
        mob_stats=_make_mob_stats(hp=100, dexterity=4),
        player_stats=_make_player_stats(strength=0),
    )
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    assert instance.mob_stats["hp"] == 92  # 100 - 8
    assert result["effect_results"][0]["value"] == 8


@pytest.mark.asyncio
async def test_dex_minimum_damage_is_one():
    """Physical 5, mob DEX=10 → raw 5, DEX reduces by 10, but min damage is 1."""
    instance = _make_instance(
        _physical_cards(value=5),
        mob_stats=_make_mob_stats(hp=100, dexterity=10),
        player_stats=_make_player_stats(strength=0),
    )
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    assert instance.mob_stats["hp"] == 99  # 100 - 1 (min)
    assert result["effect_results"][0]["value"] == 1


@pytest.mark.asyncio
async def test_dex_no_damage_when_fully_shielded():
    """Shield absorbs all damage → actual damage is 0, DEX min-1 does NOT apply."""
    # First give mob a shield
    mob = _make_mob_stats(hp=100, dexterity=5)
    mob["shield"] = 20
    instance = _make_instance(
        _physical_cards(value=10),
        mob_stats=mob,
        player_stats=_make_player_stats(strength=0),
    )
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    assert instance.mob_stats["hp"] == 100  # no HP damage
    assert result["effect_results"][0]["value"] == 0
    assert result["effect_results"][0]["shield_absorbed"] == 10


# --- DoT NOT affected by stats ---


@pytest.mark.asyncio
async def test_dot_tick_not_reduced_by_dex():
    """DoT damage bypasses DEX reduction — flat value from card."""
    instance = _make_instance(
        _dot_cards(value=6, duration=3),
        mob_stats=_make_mob_stats(hp=100, dexterity=10),
        player_stats=_make_player_stats(strength=0),
    )
    # Play the DoT card to apply the effect
    card_key = instance.hands["p1"].hand[0].card_key
    await instance.play_card("p1", card_key)

    # Now DoT ticks on next turn — process manually
    ticks = instance._process_dot_effects(instance.mob_stats, "Goblin")
    assert len(ticks) == 1
    assert ticks[0]["value"] == 6  # full damage, no DEX reduction
    assert instance.mob_stats["hp"] == 94  # 100 - 6


# --- Shield NOT affected by stats ---


@pytest.mark.asyncio
async def test_shield_value_not_modified_by_stats():
    """Shield is flat value from card, no stat bonus."""
    instance = _make_instance(
        _shield_cards(value=12),
        mob_stats=_make_mob_stats(hp=100),
        player_stats=_make_player_stats(strength=10, intelligence=10, wisdom=10),
    )
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    assert instance.participant_stats["p1"]["shield"] == 12  # flat, no bonus
    assert result["effect_results"][0]["value"] == 12


# --- Mob attack with STR and DEX ---


@pytest.mark.asyncio
async def test_mob_attack_str_bonus():
    """Mob attack = base_attack + floor(mob_str × factor). attack=10, STR=4 → 14 raw."""
    instance = CombatInstance(
        instance_id="test",
        mob_name="Goblin",
        mob_stats=_make_mob_stats(hp=100, attack=10, strength=4),
    )
    cards = _physical_cards()
    instance.add_participant("p1", _make_player_stats(hp=100), cards)

    result = instance._mob_attack_target("p1")
    assert result["damage"] == 14  # 10 + 4
    assert instance.participant_stats["p1"]["hp"] == 86  # 100 - 14


@pytest.mark.asyncio
async def test_mob_attack_with_target_dex_reduction():
    """Mob attack=10, STR=4 → raw 14. Player DEX=5 → actual=max(1, 14-5)=9."""
    instance = CombatInstance(
        instance_id="test",
        mob_name="Goblin",
        mob_stats=_make_mob_stats(hp=100, attack=10, strength=4),
    )
    cards = _physical_cards()
    instance.add_participant("p1", _make_player_stats(hp=100, dexterity=5), cards)

    result = instance._mob_attack_target("p1")
    assert result["damage"] == 9  # max(1, 14 - 5) = 9
    assert instance.participant_stats["p1"]["hp"] == 91  # 100 - 9


@pytest.mark.asyncio
async def test_mob_attack_dex_min_one():
    """Mob attack=4, STR=0 → raw 4. Player DEX=10 → actual=max(1, 4-10)=1."""
    instance = CombatInstance(
        instance_id="test",
        mob_name="Goblin",
        mob_stats=_make_mob_stats(hp=100, attack=4, strength=0),
    )
    cards = _physical_cards()
    instance.add_participant("p1", _make_player_stats(hp=100, dexterity=10), cards)

    result = instance._mob_attack_target("p1")
    assert result["damage"] == 1  # min damage
    assert instance.participant_stats["p1"]["hp"] == 99


# --- STAT_SCALING_FACTOR configuration ---


@pytest.mark.asyncio
async def test_stat_scaling_factor_half(monkeypatch):
    """STAT_SCALING_FACTOR=0.5 → floor(6 × 0.5)=3 bonus instead of 6."""
    from server.core.config import settings
    monkeypatch.setattr(settings, "STAT_SCALING_FACTOR", 0.5)

    instance = _make_instance(
        _physical_cards(value=12),
        mob_stats=_make_mob_stats(hp=100),
        player_stats=_make_player_stats(strength=6),
    )
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    # floor(6 × 0.5) = 3, total = 12 + 3 = 15
    assert instance.mob_stats["hp"] == 85  # 100 - 15
    assert result["effect_results"][0]["value"] == 15


@pytest.mark.asyncio
async def test_stat_scaling_factor_affects_dex(monkeypatch):
    """STAT_SCALING_FACTOR=0.5 → floor(10 × 0.5)=5 DEX reduction instead of 10."""
    from server.core.config import settings
    monkeypatch.setattr(settings, "STAT_SCALING_FACTOR", 0.5)

    instance = _make_instance(
        _physical_cards(value=12),
        mob_stats=_make_mob_stats(hp=100, dexterity=10),
        player_stats=_make_player_stats(strength=0),
    )
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    # raw=12, DEX reduction=floor(10×0.5)=5, actual=12-5=7
    assert instance.mob_stats["hp"] == 93  # 100 - 7
    assert result["effect_results"][0]["value"] == 7


@pytest.mark.asyncio
async def test_stat_scaling_factor_affects_heal(monkeypatch):
    """STAT_SCALING_FACTOR=0.5 → floor(6 × 0.5)=3 WIS bonus on heal."""
    from server.core.config import settings
    monkeypatch.setattr(settings, "STAT_SCALING_FACTOR", 0.5)

    instance = _make_instance(
        _heal_cards(value=15),
        mob_stats=_make_mob_stats(hp=100),
        player_stats=_make_player_stats(hp=70, max_hp=100, wisdom=6),
    )
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    # floor(6 × 0.5) = 3, total heal = 15 + 3 = 18
    assert instance.participant_stats["p1"]["hp"] == 88  # 70 + 18


@pytest.mark.asyncio
async def test_stat_scaling_factor_affects_mob_attack(monkeypatch):
    """STAT_SCALING_FACTOR=0.5 → floor(8 × 0.5)=4 mob STR bonus."""
    from server.core.config import settings
    monkeypatch.setattr(settings, "STAT_SCALING_FACTOR", 0.5)

    instance = CombatInstance(
        instance_id="test",
        mob_name="Goblin",
        mob_stats=_make_mob_stats(hp=100, attack=10, strength=8),
    )
    cards = _physical_cards()
    instance.add_participant("p1", _make_player_stats(hp=100), cards)

    result = instance._mob_attack_target("p1")
    # floor(8 × 0.5) = 4, total = 10 + 4 = 14
    assert result["damage"] == 14
    assert instance.participant_stats["p1"]["hp"] == 86
