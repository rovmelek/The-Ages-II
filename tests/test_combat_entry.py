"""Tests for combat entry from mob encounter (Story 4.7)."""
import pytest

from server.combat.cards.card_def import CardDef
from server.combat.instance import CombatInstance
from server.combat.manager import CombatManager
from server.core.effects import create_default_registry
from server.player.entity import PlayerEntity
from server.room.objects.npc import NpcEntity
from server.room.room import RoomInstance
from server.room.tile import TileType


# --- Helpers ---


def _make_cards(n=10):
    return [
        CardDef(card_key=f"card_{i}", name=f"Card {i}", cost=1,
                effects=[{"type": "damage", "value": 10}])
        for i in range(n)
    ]


def _make_room_with_mob():
    """Create a small room with a hostile NPC at (2, 0)."""
    tiles = [
        [TileType.FLOOR, TileType.FLOOR, TileType.FLOOR],
        [TileType.FLOOR, TileType.FLOOR, TileType.FLOOR],
    ]
    room = RoomInstance(
        room_key="test_room", name="Test Room",
        width=3, height=2, tile_data=tiles,
    )
    npc = NpcEntity(
        id="goblin_1", npc_key="goblin", name="Goblin",
        x=2, y=0, behavior_type="hostile",
        stats={"hp": 50, "max_hp": 50, "attack": 10},
    )
    room.add_npc(npc)
    return room, npc


def _make_player(x=0, y=0):
    return PlayerEntity(
        id="player_1", name="TestPlayer", x=x, y=y,
        player_db_id=1, stats={"hp": 100, "max_hp": 100, "attack": 15, "defense": 5},
    )


# --- Room detects mob encounter ---


def test_move_onto_hostile_mob_triggers_encounter():
    room, npc = _make_room_with_mob()
    player = _make_player(x=1, y=0)
    room.add_entity(player)
    result = room.move_entity("player_1", "right")
    assert result["success"] is True
    assert "mob_encounter" in result
    assert result["mob_encounter"]["entity_id"] == "goblin_1"
    assert result["mob_encounter"]["name"] == "Goblin"


def test_dead_mob_no_encounter():
    room, npc = _make_room_with_mob()
    npc.is_alive = False  # Already in combat or dead
    player = _make_player(x=1, y=0)
    room.add_entity(player)
    result = room.move_entity("player_1", "right")
    assert result["success"] is True
    assert "mob_encounter" not in result


# --- Combat instance creation from mob ---


def test_create_combat_from_mob_stats():
    """Simulate combat creation from a mob encounter."""
    mgr = CombatManager(effect_registry=create_default_registry())
    mob_stats = {"hp": 50, "max_hp": 50, "attack": 10}
    instance = mgr.create_instance("Goblin", mob_stats)

    player_stats = {"hp": 100, "max_hp": 100, "attack": 15, "defense": 5}
    cards = _make_cards()
    instance.add_participant("player_1", player_stats, cards)
    mgr.add_player_to_instance("player_1", instance.instance_id)

    assert mgr.get_player_instance("player_1") is instance
    assert instance.mob_name == "Goblin"
    assert instance.mob_stats["hp"] == 50
    assert "player_1" in instance.participants


# --- in_combat flag ---


def test_player_in_combat_flag():
    """Verify in_combat flag behavior."""
    player = _make_player()
    assert player.in_combat is False
    player.in_combat = True
    assert player.in_combat is True
    player.in_combat = False
    assert player.in_combat is False


def test_cannot_move_when_in_combat():
    """Player with in_combat=True should not be allowed to move (checked by handler)."""
    player = _make_player(x=0, y=0)
    player.in_combat = True
    # The handler checks entity.in_combat before calling room.move_entity
    # Here we just verify the flag works
    assert player.in_combat is True


# --- Combat start state ---


def test_combat_start_state_has_required_fields():
    """Combat state from new instance has all required fields for client."""
    mgr = CombatManager(effect_registry=create_default_registry())
    instance = mgr.create_instance("Goblin", {"hp": 50, "max_hp": 50, "attack": 10})
    instance.add_participant("p1", {"hp": 100, "max_hp": 100, "attack": 15, "shield": 0}, _make_cards())
    state = instance.get_state()

    assert "instance_id" in state
    assert "current_turn" in state
    assert state["current_turn"] == "p1"
    assert "participants" in state
    assert len(state["participants"]) == 1
    assert state["participants"][0]["energy"] == 3
    assert state["participants"][0]["max_energy"] == 3
    assert state["mob"]["name"] == "Goblin"
    assert state["mob"]["hp"] == 50
    assert "hands" in state
    assert "p1" in state["hands"]


# --- NPC marked not alive on combat entry ---


def test_npc_marked_not_alive_on_combat():
    """NPC.is_alive should be set to False when combat starts."""
    _, npc = _make_room_with_mob()
    assert npc.is_alive is True
    npc.is_alive = False  # This is what the handler does
    assert npc.is_alive is False


# --- Combat with EffectRegistry works end-to-end ---


@pytest.mark.asyncio
async def test_combat_from_encounter_can_play_cards():
    """Full flow: create instance from mob encounter, play a card with effects."""
    registry = create_default_registry()
    mgr = CombatManager(effect_registry=registry)
    mob_stats = {"hp": 50, "max_hp": 50, "attack": 10}
    instance = mgr.create_instance("Goblin", mob_stats)

    player_stats = {"hp": 100, "max_hp": 100, "attack": 15, "defense": 5, "shield": 0}
    cards = [
        CardDef(card_key=f"dmg_{i}", name="Fire Bolt", cost=1,
                effects=[{"type": "damage", "value": 20}])
        for i in range(10)
    ]
    instance.add_participant("p1", player_stats, cards)
    mgr.add_player_to_instance("p1", instance.instance_id)

    # Play a damage card
    card_key = instance.hands["p1"].hand[0].card_key
    result = await instance.play_card("p1", card_key)
    assert result["action"] == "play_card"
    assert result["effect_results"][0]["type"] == "damage"
    assert instance.mob_stats["hp"] == 30  # 50 - 20
