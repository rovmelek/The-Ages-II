"""Tests for card effect resolution in combat (Story 4.4)."""
import pytest

from server.combat.cards.card_def import CardDef
from server.combat.instance import CombatInstance
from server.core.effects import create_default_registry


# --- Helpers ---


def _registry():
    return create_default_registry()


def _make_mob_stats(hp=100, attack=10, strength=0, dexterity=0, intelligence=0, wisdom=0):
    return {"hp": hp, "max_hp": hp, "attack": attack,
            "strength": strength, "dexterity": dexterity,
            "intelligence": intelligence, "wisdom": wisdom}


def _make_player_stats(hp=100, max_hp=100, attack=15, strength=0, dexterity=0, intelligence=0, wisdom=0):
    return {"hp": hp, "max_hp": max_hp, "attack": attack, "defense": 5, "shield": 0,
            "strength": strength, "dexterity": dexterity,
            "intelligence": intelligence, "wisdom": wisdom}


def _make_two_player_instance(cards, mob_hp=100, player_hp=100, player_max_hp=100):
    """Two-player instance so P1's action doesn't trigger cycle-end mob attack."""
    instance = CombatInstance(
        instance_id="test",
        mob_name="Goblin",
        mob_stats=_make_mob_stats(hp=mob_hp),
        effect_registry=_registry(),
    )
    instance.add_participant("p1", _make_player_stats(hp=player_hp, max_hp=player_max_hp), cards)
    instance.add_participant("p2", _make_player_stats(hp=player_hp, max_hp=player_max_hp), cards)
    return instance


def _damage_cards(value=20, n=10):
    return [
        CardDef(card_key=f"dmg_{i}", name=f"Damage {i}", cost=1,
                effects=[{"type": "damage", "value": value}])
        for i in range(n)
    ]


def _heal_cards(value=15, n=10):
    return [
        CardDef(card_key=f"heal_{i}", name=f"Heal {i}", cost=1,
                effects=[{"type": "heal", "value": value}])
        for i in range(n)
    ]


def _shield_cards(value=10, n=10):
    return [
        CardDef(card_key=f"shield_{i}", name=f"Shield {i}", cost=1,
                effects=[{"type": "shield", "value": value}])
        for i in range(n)
    ]


def _multi_effect_cards(n=10):
    return [
        CardDef(card_key=f"multi_{i}", name=f"Multi {i}", cost=2,
                effects=[{"type": "damage", "value": 10}, {"type": "heal", "value": 5}])
        for i in range(n)
    ]


def _draw_cards(value=1, n=10):
    return [
        CardDef(card_key=f"draw_{i}", name=f"Draw {i}", cost=1,
                effects=[{"type": "draw", "value": value}])
        for i in range(n)
    ]


def _dot_cards(n=10):
    return [
        CardDef(card_key=f"dot_{i}", name=f"Dot {i}", cost=1,
                effects=[{"type": "dot", "subtype": "poison", "value": 5, "duration": 3}])
        for i in range(n)
    ]


# --- Damage effect resolution ---


@pytest.mark.asyncio
async def test_damage_card_reduces_mob_hp():
    instance = _make_two_player_instance(_damage_cards(value=20), mob_hp=100)
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    assert instance.mob_stats["hp"] == 80
    assert result["effect_results"][0]["type"] == "damage"
    assert result["effect_results"][0]["value"] == 20


@pytest.mark.asyncio
async def test_damage_does_not_reduce_below_zero():
    instance = _make_two_player_instance(_damage_cards(value=200), mob_hp=50)
    card_key = instance.hands["p1"].hand[0].card_key
    await instance.play_card("p1", card_key)
    assert instance.mob_stats["hp"] == 0


# --- Heal effect resolution ---


@pytest.mark.asyncio
async def test_heal_card_restores_player_hp():
    instance = _make_two_player_instance(_heal_cards(value=15), player_hp=70, player_max_hp=100)
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    assert instance.participant_stats["p1"]["hp"] == 85
    assert result["effect_results"][0]["type"] == "heal"
    assert result["effect_results"][0]["value"] == 15


@pytest.mark.asyncio
async def test_heal_capped_at_max_hp():
    instance = _make_two_player_instance(_heal_cards(value=50), player_hp=90, player_max_hp=100)
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    assert instance.participant_stats["p1"]["hp"] == 100
    assert result["effect_results"][0]["value"] == 10  # only healed 10


# --- Shield effect resolution ---


@pytest.mark.asyncio
async def test_shield_card_adds_shield():
    instance = _make_two_player_instance(_shield_cards(value=10))
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    assert instance.participant_stats["p1"]["shield"] == 10
    assert result["effect_results"][0]["type"] == "shield"


@pytest.mark.asyncio
async def test_shield_stacks_across_turns():
    """Shield from two different turns stacks (using two-player to avoid mob attack between)."""
    instance = _make_two_player_instance(_shield_cards(value=10))
    # P1 plays shield
    card_key1 = instance.hands["p1"].hand[0].card_key
    await instance.play_card("p1", card_key1)
    assert instance.participant_stats["p1"]["shield"] == 10

    # P2 plays (to complete cycle — mob attacks random player)
    card_key2 = instance.hands["p2"].hand[0].card_key
    await instance.play_card("p2", card_key2)

    # P1 plays another shield — stacks on top of whatever remains
    old_shield = instance.participant_stats["p1"]["shield"]
    card_key3 = instance.hands["p1"].hand[0].card_key
    await instance.play_card("p1", card_key3)
    assert instance.participant_stats["p1"]["shield"] == old_shield + 10


# --- Multi-effect card resolution ---


@pytest.mark.asyncio
async def test_multi_effect_card():
    instance = _make_two_player_instance(_multi_effect_cards(), mob_hp=100, player_hp=80, player_max_hp=100)
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    # Damage effect applied to mob
    assert instance.mob_stats["hp"] == 90
    # Heal effect applied to player
    assert instance.participant_stats["p1"]["hp"] == 85
    assert len(result["effect_results"]) == 2
    assert result["effect_results"][0]["type"] == "damage"
    assert result["effect_results"][1]["type"] == "heal"


# --- Draw effect resolution ---


@pytest.mark.asyncio
async def test_draw_effect_draws_cards():
    instance = _make_two_player_instance(_draw_cards(value=2))
    initial_hand_size = len(instance.hands["p1"].hand)
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    # play_card removes 1 from hand, draws 1 replacement, then draw effect draws 2 more
    # Net: initial_hand_size - 1 + 1 (replacement) + 2 (draw effect) = initial + 2
    assert len(instance.hands["p1"].hand) == initial_hand_size + 2
    assert result["effect_results"][0]["type"] == "draw"
    assert result["effect_results"][0]["value"] == 2


# --- DoT effect resolution ---


@pytest.mark.asyncio
async def test_dot_effect_adds_to_mob():
    instance = _make_two_player_instance(_dot_cards())
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    assert result["effect_results"][0]["type"] == "dot"
    assert "active_effects" in instance.mob_stats
    assert len(instance.mob_stats["active_effects"]) == 1
    assert instance.mob_stats["active_effects"][0]["subtype"] == "poison"
    assert instance.mob_stats["active_effects"][0]["remaining"] == 3


# --- No registry graceful handling ---


@pytest.mark.asyncio
async def test_no_registry_returns_empty_effects():
    """When no EffectRegistry is provided, effects are not resolved."""
    cards = _damage_cards(value=20)
    instance = CombatInstance(
        instance_id="test", mob_name="Mob",
        mob_stats=_make_mob_stats(hp=100),
    )
    instance.add_participant("p1", _make_player_stats(), cards)
    instance.add_participant("p2", _make_player_stats(), cards)
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    assert result["effect_results"] == []
    # Mob HP unchanged since no effects resolved
    assert instance.mob_stats["hp"] == 100


# --- Effect results included in play_card result ---


@pytest.mark.asyncio
async def test_effect_results_in_play_card():
    instance = _make_two_player_instance(_damage_cards(value=10))
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    assert "effect_results" in result
    assert isinstance(result["effect_results"], list)
    assert len(result["effect_results"]) == 1
