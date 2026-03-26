"""Tests for combat instance and turn structure (Story 4.3)."""
import pytest

from server.combat.cards.card_def import CardDef
from server.combat.instance import CombatInstance
from server.combat.manager import CombatManager


# --- Helpers ---


def _make_cards(n: int = 10) -> list[CardDef]:
    return [
        CardDef(card_key=f"card_{i}", name=f"Card {i}", cost=1, effects=[{"type": "damage", "value": 10}])
        for i in range(n)
    ]


def _make_mob_stats(hp=50, attack=10):
    return {"hp": hp, "max_hp": hp, "attack": attack}


def _make_player_stats(hp=100, attack=15):
    return {"hp": hp, "max_hp": hp, "attack": attack, "defense": 5}


def _make_instance_with_player():
    instance = CombatInstance(
        instance_id="test_combat",
        mob_name="Goblin",
        mob_stats=_make_mob_stats(),
    )
    cards = _make_cards()
    instance.add_participant("player_1", _make_player_stats(), cards)
    return instance


def _make_instance_with_two_players():
    instance = CombatInstance(
        instance_id="test_combat",
        mob_name="Goblin",
        mob_stats=_make_mob_stats(),
    )
    cards = _make_cards()
    instance.add_participant("player_1", _make_player_stats(), cards)
    instance.add_participant("player_2", _make_player_stats(), cards)
    return instance


# --- CombatInstance creation ---


def test_create_instance():
    instance = CombatInstance(
        instance_id="test_1",
        mob_name="Goblin",
        mob_stats=_make_mob_stats(hp=50, attack=10),
    )
    assert instance.instance_id == "test_1"
    assert instance.mob_name == "Goblin"
    assert instance.mob_stats["hp"] == 50


def test_add_participant():
    instance = _make_instance_with_player()
    assert "player_1" in instance.participants
    assert instance.participant_stats["player_1"]["hp"] == 100
    assert "player_1" in instance.hands
    assert len(instance.hands["player_1"].hand) == 5


def test_add_participant_initializes_shield():
    instance = CombatInstance(
        instance_id="test", mob_name="Mob", mob_stats=_make_mob_stats()
    )
    instance.add_participant("p1", {"hp": 100, "max_hp": 100, "attack": 10}, _make_cards())
    assert instance.participant_stats["p1"]["shield"] == 0


# --- Turn order ---


def test_get_current_turn_single_player():
    instance = _make_instance_with_player()
    assert instance.get_current_turn() == "player_1"


def test_get_current_turn_two_players():
    instance = _make_instance_with_two_players()
    assert instance.get_current_turn() == "player_1"


# --- play_card ---


@pytest.mark.asyncio
async def test_play_card_advances_turn():
    instance = _make_instance_with_two_players()
    card_key = instance.hands["player_1"].hand[0].card_key
    result = await instance.play_card("player_1", card_key)
    assert result["action"] == "play_card"
    assert result["entity_id"] == "player_1"
    assert result["card"]["card_key"] == card_key
    # Turn should now be player_2
    assert instance.get_current_turn() == "player_2"


@pytest.mark.asyncio
async def test_play_card_wrong_turn_raises():
    instance = _make_instance_with_two_players()
    card_key = instance.hands["player_2"].hand[0].card_key
    with pytest.raises(ValueError, match="Not your turn"):
        await instance.play_card("player_2", card_key)


@pytest.mark.asyncio
async def test_play_card_invalid_card_raises():
    instance = _make_instance_with_player()
    with pytest.raises(ValueError, match="Card not in hand"):
        await instance.play_card("player_1", "nonexistent")


# --- pass_turn ---


@pytest.mark.asyncio
async def test_pass_turn_mob_attacks_passer():
    instance = _make_instance_with_player()
    result = await instance.pass_turn("player_1")
    assert result["action"] == "pass_turn"
    assert result["mob_attack"]["target"] == "player_1"
    assert result["mob_attack"]["damage"] > 0
    # HP should be reduced
    assert instance.participant_stats["player_1"]["hp"] < 100


@pytest.mark.asyncio
async def test_pass_turn_wrong_turn_raises():
    instance = _make_instance_with_two_players()
    with pytest.raises(ValueError, match="Not your turn"):
        await instance.pass_turn("player_2")


# --- Full cycle mob attack ---


@pytest.mark.asyncio
async def test_full_cycle_triggers_mob_attack():
    instance = _make_instance_with_two_players()
    # Player 1 plays card
    card_key = instance.hands["player_1"].hand[0].card_key
    result1 = await instance.play_card("player_1", card_key)
    assert "mob_attack" not in result1  # not yet a full cycle

    # Player 2 plays card — completes cycle
    card_key2 = instance.hands["player_2"].hand[0].card_key
    result2 = await instance.play_card("player_2", card_key2)
    assert "mob_attack" in result2  # cycle complete, mob attacks


@pytest.mark.asyncio
async def test_single_player_cycle():
    instance = _make_instance_with_player()
    # Single player — each action is a full cycle
    card_key = instance.hands["player_1"].hand[0].card_key
    result = await instance.play_card("player_1", card_key)
    assert "mob_attack" in result  # one player = one action = full cycle


# --- Turn alternation (two players) ---


@pytest.mark.asyncio
async def test_turn_alternation():
    instance = _make_instance_with_two_players()
    assert instance.get_current_turn() == "player_1"

    card_key = instance.hands["player_1"].hand[0].card_key
    await instance.play_card("player_1", card_key)
    assert instance.get_current_turn() == "player_2"

    card_key2 = instance.hands["player_2"].hand[0].card_key
    await instance.play_card("player_2", card_key2)
    # After cycle, back to player_1
    assert instance.get_current_turn() == "player_1"


# --- remove_participant ---


def test_remove_participant():
    instance = _make_instance_with_two_players()
    instance.remove_participant("player_1")
    assert "player_1" not in instance.participants
    assert instance.get_current_turn() == "player_2"


# --- get_state ---


def test_get_state_structure():
    instance = _make_instance_with_player()
    state = instance.get_state()
    assert state["instance_id"] == "test_combat"
    assert state["current_turn"] == "player_1"
    assert len(state["participants"]) == 1
    assert state["participants"][0]["entity_id"] == "player_1"
    assert state["participants"][0]["hp"] == 100
    assert state["mob"]["name"] == "Goblin"
    assert state["mob"]["hp"] == 50
    assert "player_1" in state["hands"]


# --- is_finished ---


def test_is_finished_mob_dead():
    instance = _make_instance_with_player()
    instance.mob_stats["hp"] = 0
    assert instance.is_finished is True


def test_is_finished_all_players_dead():
    instance = _make_instance_with_player()
    instance.participant_stats["player_1"]["hp"] = 0
    assert instance.is_finished is True


def test_not_finished_during_combat():
    instance = _make_instance_with_player()
    assert instance.is_finished is False


def test_is_finished_no_participants():
    instance = CombatInstance(
        instance_id="test", mob_name="Mob", mob_stats=_make_mob_stats()
    )
    assert instance.is_finished is True


# --- CombatManager ---


def test_combat_manager_create_and_get():
    mgr = CombatManager()
    instance = mgr.create_instance("Goblin", _make_mob_stats())
    assert mgr.get_instance(instance.instance_id) is instance


def test_combat_manager_player_mapping():
    mgr = CombatManager()
    instance = mgr.create_instance("Goblin", _make_mob_stats())
    instance.add_participant("player_1", _make_player_stats(), _make_cards())
    mgr.add_player_to_instance("player_1", instance.instance_id)
    assert mgr.get_player_instance("player_1") is instance


def test_combat_manager_remove_instance():
    mgr = CombatManager()
    instance = mgr.create_instance("Goblin", _make_mob_stats())
    instance.add_participant("player_1", _make_player_stats(), _make_cards())
    mgr.add_player_to_instance("player_1", instance.instance_id)
    mgr.remove_instance(instance.instance_id)
    assert mgr.get_instance(instance.instance_id) is None
    assert mgr.get_player_instance("player_1") is None


def test_combat_manager_remove_player():
    mgr = CombatManager()
    instance = mgr.create_instance("Goblin", _make_mob_stats())
    mgr.add_player_to_instance("player_1", instance.instance_id)
    mgr.remove_player("player_1")
    assert mgr.get_player_instance("player_1") is None


def test_combat_manager_unknown_instance():
    mgr = CombatManager()
    assert mgr.get_instance("nonexistent") is None
    assert mgr.get_player_instance("nonexistent") is None


# --- Code review fixes ---


@pytest.mark.asyncio
async def test_remove_current_turn_player_advances_to_next():
    """Fix #11: removing current-turn player should advance to next, not previous."""
    instance = CombatInstance(
        instance_id="test", mob_name="Mob", mob_stats=_make_mob_stats()
    )
    cards = _make_cards()
    instance.add_participant("A", _make_player_stats(), cards)
    instance.add_participant("B", _make_player_stats(), cards)
    instance.add_participant("C", _make_player_stats(), cards)
    # Turn is A's (index 0). Play A's card to advance to B.
    card_key = instance.hands["A"].hand[0].card_key
    await instance.play_card("A", card_key)
    assert instance.get_current_turn() == "B"
    # Remove B — C should be next, not A
    instance.remove_participant("B")
    assert instance.get_current_turn() == "C"


@pytest.mark.asyncio
async def test_dead_player_cannot_play_card():
    """Fix #16: dead players can't take actions."""
    instance = _make_instance_with_player()
    instance.participant_stats["player_1"]["hp"] = 0
    card_key = instance.hands["player_1"].hand[0].card_key
    with pytest.raises(ValueError, match="You are dead"):
        await instance.play_card("player_1", card_key)


@pytest.mark.asyncio
async def test_dead_player_cannot_pass():
    """Fix #16: dead players can't take actions."""
    instance = _make_instance_with_player()
    instance.participant_stats["player_1"]["hp"] = 0
    with pytest.raises(ValueError, match="You are dead"):
        await instance.pass_turn("player_1")


# --- Epic 4 code review fixes ---


# --- Energy system ---


def test_add_participant_initializes_energy():
    instance = CombatInstance(
        instance_id="test", mob_name="Mob", mob_stats=_make_mob_stats()
    )
    instance.add_participant("p1", {"hp": 100, "max_hp": 100, "attack": 10}, _make_cards())
    assert instance.participant_stats["p1"]["energy"] == 3
    assert instance.participant_stats["p1"]["max_energy"] == 3


def test_get_state_includes_energy():
    instance = _make_instance_with_player()
    state = instance.get_state()
    p = state["participants"][0]
    assert "energy" in p
    assert "max_energy" in p
    assert p["energy"] == 3
    assert p["max_energy"] == 3


@pytest.mark.asyncio
async def test_play_card_deducts_energy():
    instance = _make_instance_with_two_players()
    assert instance.participant_stats["player_1"]["energy"] == 3
    card_key = instance.hands["player_1"].hand[0].card_key
    await instance.play_card("player_1", card_key)
    # Cards cost 1, so energy should be 2
    assert instance.participant_stats["player_1"]["energy"] == 2


@pytest.mark.asyncio
async def test_play_card_not_enough_energy():
    instance = _make_instance_with_two_players()
    # Drain energy to 0
    instance.participant_stats["player_1"]["energy"] = 0
    card_key = instance.hands["player_1"].hand[0].card_key
    with pytest.raises(ValueError, match="Not enough energy"):
        await instance.play_card("player_1", card_key)


@pytest.mark.asyncio
async def test_cycle_regenerates_energy():
    instance = _make_instance_with_two_players()
    # Play cards for both players — cost 1 each
    card_key1 = instance.hands["player_1"].hand[0].card_key
    await instance.play_card("player_1", card_key1)
    assert instance.participant_stats["player_1"]["energy"] == 2

    card_key2 = instance.hands["player_2"].hand[0].card_key
    await instance.play_card("player_2", card_key2)
    # Cycle complete — energy regen (+3, capped at max 3)
    assert instance.participant_stats["player_1"]["energy"] == 3
    assert instance.participant_stats["player_2"]["energy"] == 3


@pytest.mark.asyncio
async def test_pass_turn_no_energy_cost():
    instance = _make_instance_with_two_players()
    instance.participant_stats["player_1"]["energy"] = 1
    await instance.pass_turn("player_1")
    # Energy unchanged by passing
    assert instance.participant_stats["player_1"]["energy"] == 1


@pytest.mark.asyncio
async def test_use_item_no_energy_cost():
    from unittest.mock import MagicMock
    instance = _make_instance_with_two_players()
    instance.participant_stats["player_1"]["energy"] = 1
    item_def = MagicMock()
    item_def.item_key = "potion"
    item_def.name = "Potion"
    item_def.effects = []
    await instance.use_item("player_1", item_def)
    # Energy unchanged by using item
    assert instance.participant_stats["player_1"]["energy"] == 1


@pytest.mark.asyncio
async def test_dead_player_skipped_in_turn_order():
    """After mob attack kills a player, their turn is automatically skipped."""
    instance = CombatInstance(
        instance_id="test", mob_name="Mob", mob_stats=_make_mob_stats(attack=0)
    )
    cards = _make_cards()
    instance.add_participant("A", _make_player_stats(), cards)
    instance.add_participant("B", _make_player_stats(hp=1), cards)  # Will die if attacked
    instance.add_participant("C", _make_player_stats(), cards)
    # Kill B manually to simulate mob attack
    instance.participant_stats["B"]["hp"] = 0
    # A plays — turn should advance past dead B to C
    card_key = instance.hands["A"].hand[0].card_key
    await instance.play_card("A", card_key)
    assert instance.get_current_turn() == "C"
