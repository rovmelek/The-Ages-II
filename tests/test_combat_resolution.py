"""Tests for combat resolution and rewards (Story 4.5)."""
import pytest

from server.combat.cards.card_def import CardDef
from server.combat.instance import CombatInstance
from server.combat.manager import CombatManager
from server.core.effects import create_default_registry


# --- Helpers ---


def _registry():
    return create_default_registry()


def _make_mob_stats(hp=50, attack=10, strength=0, dexterity=0, intelligence=0, wisdom=0):
    return {"hp": hp, "max_hp": hp, "attack": attack,
            "strength": strength, "dexterity": dexterity,
            "intelligence": intelligence, "wisdom": wisdom}


def _make_player_stats(hp=100, strength=0, dexterity=0, intelligence=0, wisdom=0):
    return {"hp": hp, "max_hp": 100, "attack": 15, "defense": 5, "shield": 0,
            "strength": strength, "dexterity": dexterity,
            "intelligence": intelligence, "wisdom": wisdom}


def _damage_cards(value=20, n=10):
    return [
        CardDef(card_key=f"dmg_{i}", name=f"Damage {i}", cost=1,
                effects=[{"type": "damage", "value": value}])
        for i in range(n)
    ]


def _heal_cards(n=10):
    return [
        CardDef(card_key=f"heal_{i}", name=f"Heal {i}", cost=1,
                effects=[{"type": "heal", "value": 10}])
        for i in range(n)
    ]


# --- get_combat_end_result ---


def test_combat_end_result_victory():
    instance = CombatInstance(
        instance_id="test", mob_name="Mob", mob_stats=_make_mob_stats(hp=0)
    )
    instance.add_participant("p1", _make_player_stats(), _damage_cards())
    result = instance.get_combat_end_result()
    assert result is not None
    assert result["victory"] is True
    assert result["rewards_per_player"]["p1"]["xp"] == 0  # mob_hit_dice defaults to 0


def test_combat_end_result_defeat():
    instance = CombatInstance(
        instance_id="test", mob_name="Mob", mob_stats=_make_mob_stats()
    )
    instance.add_participant("p1", _make_player_stats(hp=0), _damage_cards())
    result = instance.get_combat_end_result()
    assert result is not None
    assert result["victory"] is False
    assert result["rewards_per_player"] == {}


def test_combat_end_result_not_finished():
    instance = CombatInstance(
        instance_id="test", mob_name="Mob", mob_stats=_make_mob_stats()
    )
    instance.add_participant("p1", _make_player_stats(), _damage_cards())
    assert instance.get_combat_end_result() is None


# --- Victory via card play ---


@pytest.mark.asyncio
async def test_victory_by_killing_mob():
    """Playing a damage card that kills the mob ends combat with victory."""
    instance = CombatInstance(
        instance_id="test", mob_name="Mob",
        mob_stats=_make_mob_stats(hp=10),
        effect_registry=_registry(),
    )
    # Two players so P1's action doesn't trigger cycle mob attack
    instance.add_participant("p1", _make_player_stats(), _damage_cards(value=20))
    instance.add_participant("p2", _make_player_stats(), _damage_cards(value=20))
    card_key = instance.hands["p1"].hand[0].card_key
    await instance.play_card("p1", card_key)
    assert instance.mob_stats["hp"] == 0
    assert instance.is_finished is True
    end = instance.get_combat_end_result()
    assert end["victory"] is True
    assert end["rewards_per_player"]["p1"]["xp"] == 0  # mob_hit_dice defaults to 0


# --- Defeat via mob attack ---


@pytest.mark.asyncio
async def test_defeat_all_players_dead():
    """All players reaching 0 HP results in defeat."""
    instance = CombatInstance(
        instance_id="test", mob_name="Mob",
        mob_stats=_make_mob_stats(hp=100, attack=200),  # kills in one hit
        effect_registry=_registry(),
    )
    instance.add_participant("p1", _make_player_stats(hp=10), _heal_cards())
    # Single player — pass triggers mob attack which kills
    await instance.pass_turn("p1")
    assert instance.participant_stats["p1"]["hp"] == 0
    assert instance.is_finished is True
    end = instance.get_combat_end_result()
    assert end["victory"] is False


# --- CombatManager cleanup ---


def test_manager_remove_instance_cleans_up():
    mgr = CombatManager()
    instance = mgr.create_instance("Mob", _make_mob_stats())
    instance.add_participant("p1", _make_player_stats(), _damage_cards())
    mgr.add_player_to_instance("p1", instance.instance_id)
    instance.add_participant("p2", _make_player_stats(), _damage_cards())
    mgr.add_player_to_instance("p2", instance.instance_id)

    mgr.remove_instance(instance.instance_id)
    assert mgr.get_instance(instance.instance_id) is None
    assert mgr.get_player_instance("p1") is None
    assert mgr.get_player_instance("p2") is None


# --- Combat end after multiple players die ---


@pytest.mark.asyncio
async def test_combat_not_finished_if_one_player_alive():
    """Combat continues as long as at least one player is alive."""
    instance = CombatInstance(
        instance_id="test", mob_name="Mob",
        mob_stats=_make_mob_stats(hp=100),
        effect_registry=_registry(),
    )
    instance.add_participant("p1", _make_player_stats(hp=0), _damage_cards())
    instance.add_participant("p2", _make_player_stats(hp=50), _damage_cards())
    # p1 is dead but p2 is alive — combat not finished
    assert instance.is_finished is False
    end = instance.get_combat_end_result()
    assert end is None
