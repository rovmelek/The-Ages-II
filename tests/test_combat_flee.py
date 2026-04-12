"""Tests for flee combat action (Story 4.6)."""
import pytest

from server.combat.cards.card_def import CardDef
from server.combat.instance import CombatInstance
from server.combat.manager import CombatManager


# --- Helpers ---


def _make_cards(n=10):
    return [
        CardDef(card_key=f"card_{i}", name=f"Card {i}", cost=1,
                effects=[{"type": "damage", "value": 10}])
        for i in range(n)
    ]


def _make_mob_stats(hp=50, attack=10, strength=0, dexterity=0, intelligence=0, wisdom=0):
    return {"hp": hp, "max_hp": hp, "attack": attack,
            "strength": strength, "dexterity": dexterity,
            "intelligence": intelligence, "wisdom": wisdom}


def _make_player_stats(hp=100, strength=0, dexterity=0, intelligence=0, wisdom=0):
    return {"hp": hp, "max_hp": 100, "attack": 15, "defense": 5, "shield": 0,
            "strength": strength, "dexterity": dexterity,
            "intelligence": intelligence, "wisdom": wisdom}


# --- Flee removes participant ---


def test_flee_removes_participant():
    instance = CombatInstance(
        instance_id="test", mob_name="Mob", mob_stats=_make_mob_stats()
    )
    instance.add_participant("p1", _make_player_stats(), _make_cards())
    instance.add_participant("p2", _make_player_stats(), _make_cards())
    instance.remove_participant("p1")
    assert "p1" not in instance.participants
    assert "p2" in instance.participants


def test_flee_updates_turn_order():
    instance = CombatInstance(
        instance_id="test", mob_name="Mob", mob_stats=_make_mob_stats()
    )
    instance.add_participant("p1", _make_player_stats(), _make_cards())
    instance.add_participant("p2", _make_player_stats(), _make_cards())
    assert instance.get_current_turn() == "p1"
    instance.remove_participant("p1")
    assert instance.get_current_turn() == "p2"


# --- Flee from CombatManager ---


def test_flee_removes_from_manager():
    mgr = CombatManager()
    instance = mgr.create_instance("Mob", _make_mob_stats())
    instance.add_participant("p1", _make_player_stats(), _make_cards())
    mgr.add_player_to_instance("p1", instance.instance_id)
    instance.add_participant("p2", _make_player_stats(), _make_cards())
    mgr.add_player_to_instance("p2", instance.instance_id)

    # P1 flees
    instance.remove_participant("p1")
    mgr.remove_player("p1")
    assert mgr.get_player_instance("p1") is None
    # P2 still in combat
    assert mgr.get_player_instance("p2") is instance


def test_last_player_flee_allows_cleanup():
    mgr = CombatManager()
    instance = mgr.create_instance("Mob", _make_mob_stats())
    iid = instance.instance_id
    instance.add_participant("p1", _make_player_stats(), _make_cards())
    mgr.add_player_to_instance("p1", iid)

    # P1 flees — last participant
    instance.remove_participant("p1")
    mgr.remove_player("p1")
    assert len(instance.participants) == 0

    # Instance can be cleaned up
    mgr.remove_instance(iid)
    assert mgr.get_instance(iid) is None


# --- Combat continues for remaining players ---


@pytest.mark.asyncio
async def test_combat_continues_after_flee():
    """Remaining player can still play cards after one flees."""
    instance = CombatInstance(
        instance_id="test", mob_name="Mob", mob_stats=_make_mob_stats()
    )
    instance.add_participant("p1", _make_player_stats(), _make_cards())
    instance.add_participant("p2", _make_player_stats(), _make_cards())

    # P1 flees
    instance.remove_participant("p1")
    assert instance.get_current_turn() == "p2"

    # P2 can still play
    card_key = instance.hands["p2"].hand[0].card_key
    result = await instance.play_card("p2", card_key)
    assert result["action"] == "play_card"


# --- is_finished after all flee ---


def test_is_finished_no_participants_after_flee():
    instance = CombatInstance(
        instance_id="test", mob_name="Mob", mob_stats=_make_mob_stats()
    )
    instance.add_participant("p1", _make_player_stats(), _make_cards())
    instance.remove_participant("p1")
    assert instance.is_finished is True
