"""Tests for the shared loot system (Story 10.7)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.items.loot import LOOT_TABLES, generate_loot


# ---------------------------------------------------------------------------
# generate_loot unit tests
# ---------------------------------------------------------------------------

def test_generate_loot_slime():
    items = generate_loot("slime_loot")
    assert len(items) == 1
    assert items[0]["item_key"] == "healing_potion"
    assert items[0]["quantity"] == 1


def test_generate_loot_goblin():
    items = generate_loot("goblin_loot")
    assert len(items) == 1
    assert items[0]["item_key"] == "iron_shard"


def test_generate_loot_bat():
    items = generate_loot("bat_loot")
    assert len(items) == 1
    assert items[0]["item_key"] == "antidote"


def test_generate_loot_troll():
    items = generate_loot("troll_loot")
    assert len(items) == 2
    keys = {i["item_key"] for i in items}
    assert keys == {"healing_potion", "iron_shard"}


def test_generate_loot_dragon():
    items = generate_loot("dragon_loot")
    assert len(items) == 2
    keys = {i["item_key"] for i in items}
    assert keys == {"fire_essence", "healing_potion"}
    for item in items:
        assert item["quantity"] == 2


def test_generate_loot_unknown_table():
    items = generate_loot("nonexistent_table")
    assert items == []


def test_generate_loot_empty_string():
    items = generate_loot("")
    assert items == []


def test_generate_loot_returns_list_copy():
    """generate_loot returns a copy of the list, not a reference."""
    items1 = generate_loot("slime_loot")
    items2 = generate_loot("slime_loot")
    assert items1 is not items2
    assert items1 == items2


def test_generate_loot_chest_tables_still_work():
    """Chest loot tables are still available after extraction."""
    items = generate_loot("common_chest")
    assert len(items) == 2
    keys = {i["item_key"] for i in items}
    assert "healing_potion" in keys
    assert "iron_shard" in keys


def test_all_npc_loot_tables_present():
    """All NPC loot table keys referenced in base_npcs.json exist."""
    expected_keys = {"slime_loot", "goblin_loot", "bat_loot", "troll_loot", "dragon_loot"}
    for key in expected_keys:
        assert key in LOOT_TABLES, f"Missing loot table: {key}"
        assert len(LOOT_TABLES[key]) > 0, f"Empty loot table: {key}"


# ---------------------------------------------------------------------------
# Combat loot integration tests
# ---------------------------------------------------------------------------

def _make_game():
    from server.app import Game
    return Game()


def _make_npc(npc_id="npc_1", loot_table="slime_loot"):
    from server.room.objects.npc import NpcEntity
    return NpcEntity(
        id=npc_id, npc_key="slime", name="Slime",
        x=2, y=2, behavior_type="hostile",
        stats={"hp": 0, "max_hp": 50, "attack": 5},
        loot_table=loot_table,
    )


def _make_combat_instance(npc_id="npc_1", room_key="test_room"):
    """Create a mock CombatInstance that reports victory."""
    instance = MagicMock()
    instance.npc_id = npc_id
    instance.room_key = room_key
    instance.participants = ["player_1"]
    instance.participant_stats = {
        "player_1": {"hp": 80, "max_hp": 100, "attack": 10},
    }
    instance.instance_id = "combat_1"
    instance.get_combat_end_result.return_value = {
        "victory": True,
        "rewards": {"xp": 25},
    }
    return instance


@pytest.mark.asyncio
async def test_combat_victory_includes_loot():
    """Combat victory with an NPC that has a loot_table includes loot in combat_end."""
    from server.net.handlers.combat import _check_combat_end
    from server.player.entity import PlayerEntity
    from server.items.inventory import Inventory

    game = _make_game()
    npc = _make_npc()
    instance = _make_combat_instance()

    # Set up room with NPC
    room = MagicMock()
    room.get_npc.return_value = npc
    room.get_state.return_value = {"room_key": "test_room", "tiles": [], "entities": [], "objects": []}
    game.room_manager._rooms = {"test_room": room}
    game.room_manager.get_room = MagicMock(return_value=room)

    # Set up player entity
    entity = PlayerEntity(id="player_1", name="hero", x=2, y=2, player_db_id=1)
    entity.stats = {"hp": 80, "max_hp": 100, "attack": 10, "xp": 0}
    inventory = Inventory()
    game.player_entities["player_1"] = {
        "entity": entity, "room_key": "test_room",
        "inventory": inventory, "db_id": 1,
    }

    ws = AsyncMock()
    game.connection_manager.connect("player_1", ws, "test_room")
    game.combat_manager._player_to_instance["player_1"] = "combat_1"
    game.combat_manager._instances["combat_1"] = instance

    # Mock DB calls
    mock_player = AsyncMock()
    mock_player.inventory = {}

    mock_item = MagicMock()
    mock_item.item_key = "healing_potion"
    mock_item.name = "Healing Potion"
    mock_item.category = "consumable"
    mock_item.stackable = True
    mock_item.charges = 3
    mock_item.effects = [{"type": "heal", "value": 25}]
    mock_item.usable_in_combat = True
    mock_item.usable_outside_combat = True
    mock_item.description = "Heals 25 HP"

    with patch("server.net.handlers.combat.async_session") as mock_session, \
         patch("server.net.handlers.combat.player_repo") as mock_repo, \
         patch("server.net.handlers.combat.items_repo") as mock_items_repo:
        mock_sess = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_repo.get_by_id = AsyncMock(return_value=mock_player)
        mock_repo.update_stats = AsyncMock()
        mock_items_repo.get_all = AsyncMock(return_value=[mock_item])

        game.kill_npc = AsyncMock()

        await _check_combat_end(instance, game)

    # Find the combat_end message
    combat_end_msg = None
    for call in ws.send_json.call_args_list:
        msg = call.args[0]
        if msg.get("type") == "combat_end":
            combat_end_msg = msg
            break

    assert combat_end_msg is not None
    assert combat_end_msg["victory"] is True
    assert "loot" in combat_end_msg
    assert len(combat_end_msg["loot"]) == 1
    assert combat_end_msg["loot"][0]["item_key"] == "healing_potion"
    assert combat_end_msg["loot"][0]["quantity"] == 1


@pytest.mark.asyncio
async def test_combat_victory_no_loot_table():
    """Combat victory with NPC that has empty loot_table produces no loot."""
    from server.net.handlers.combat import _check_combat_end
    from server.player.entity import PlayerEntity
    from server.items.inventory import Inventory

    game = _make_game()
    npc = _make_npc(loot_table="")
    instance = _make_combat_instance()

    room = MagicMock()
    room.get_npc.return_value = npc
    room.get_state.return_value = {"room_key": "test_room", "tiles": [], "entities": [], "objects": []}
    game.room_manager._rooms = {"test_room": room}
    game.room_manager.get_room = MagicMock(return_value=room)

    entity = PlayerEntity(id="player_1", name="hero", x=2, y=2, player_db_id=1)
    entity.stats = {"hp": 80, "max_hp": 100, "attack": 10, "xp": 0}
    inventory = Inventory()
    game.player_entities["player_1"] = {
        "entity": entity, "room_key": "test_room",
        "inventory": inventory, "db_id": 1,
    }

    ws = AsyncMock()
    game.connection_manager.connect("player_1", ws, "test_room")
    game.combat_manager._player_to_instance["player_1"] = "combat_1"
    game.combat_manager._instances["combat_1"] = instance

    with patch("server.net.handlers.combat.async_session") as mock_session, \
         patch("server.net.handlers.combat.player_repo") as mock_repo, \
         patch("server.net.handlers.combat.items_repo"):
        mock_sess = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_repo.update_stats = AsyncMock()

        game.kill_npc = AsyncMock()

        await _check_combat_end(instance, game)

    combat_end_msg = None
    for call in ws.send_json.call_args_list:
        msg = call.args[0]
        if msg.get("type") == "combat_end":
            combat_end_msg = msg
            break

    assert combat_end_msg is not None
    assert "loot" not in combat_end_msg


@pytest.mark.asyncio
async def test_combat_victory_loot_updates_inventory():
    """Loot is added to player's runtime inventory on victory."""
    from server.net.handlers.combat import _check_combat_end
    from server.player.entity import PlayerEntity
    from server.items.inventory import Inventory

    game = _make_game()
    npc = _make_npc(loot_table="goblin_loot")  # drops iron_shard x1
    instance = _make_combat_instance()

    room = MagicMock()
    room.get_npc.return_value = npc
    room.get_state.return_value = {"room_key": "test_room", "tiles": [], "entities": [], "objects": []}
    game.room_manager._rooms = {"test_room": room}
    game.room_manager.get_room = MagicMock(return_value=room)

    entity = PlayerEntity(id="player_1", name="hero", x=2, y=2, player_db_id=1)
    entity.stats = {"hp": 80, "max_hp": 100, "attack": 10, "xp": 0}
    inventory = Inventory()
    game.player_entities["player_1"] = {
        "entity": entity, "room_key": "test_room",
        "inventory": inventory, "db_id": 1,
    }

    ws = AsyncMock()
    game.connection_manager.connect("player_1", ws, "test_room")
    game.combat_manager._player_to_instance["player_1"] = "combat_1"
    game.combat_manager._instances["combat_1"] = instance

    mock_player = AsyncMock()
    mock_player.inventory = {}

    mock_item = MagicMock()
    mock_item.item_key = "iron_shard"
    mock_item.name = "Iron Shard"
    mock_item.category = "material"
    mock_item.stackable = True
    mock_item.charges = 0
    mock_item.effects = []
    mock_item.usable_in_combat = False
    mock_item.usable_outside_combat = False
    mock_item.description = "A shard of iron"

    with patch("server.net.handlers.combat.async_session") as mock_session, \
         patch("server.net.handlers.combat.player_repo") as mock_repo, \
         patch("server.net.handlers.combat.items_repo") as mock_items_repo:
        mock_sess = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_repo.get_by_id = AsyncMock(return_value=mock_player)
        mock_repo.update_stats = AsyncMock()
        mock_items_repo.get_all = AsyncMock(return_value=[mock_item])

        game.kill_npc = AsyncMock()

        await _check_combat_end(instance, game)

    # Runtime inventory should have the loot
    assert inventory.has_item("iron_shard")
    assert inventory.get_quantity("iron_shard") == 1

    # DB inventory should have been updated
    assert mock_player.inventory.get("iron_shard") == 1


@pytest.mark.asyncio
async def test_combat_victory_multi_player_same_loot():
    """Multiple players in combat each receive the same loot."""
    from server.net.handlers.combat import _check_combat_end
    from server.player.entity import PlayerEntity
    from server.items.inventory import Inventory

    game = _make_game()
    npc = _make_npc(loot_table="slime_loot")
    instance = _make_combat_instance()
    instance.participants = ["player_1", "player_2"]
    instance.participant_stats = {
        "player_1": {"hp": 80, "max_hp": 100, "attack": 10},
        "player_2": {"hp": 60, "max_hp": 100, "attack": 10},
    }

    room = MagicMock()
    room.get_npc.return_value = npc
    room.get_state.return_value = {"room_key": "test_room", "tiles": [], "entities": [], "objects": []}
    game.room_manager._rooms = {"test_room": room}
    game.room_manager.get_room = MagicMock(return_value=room)

    inv1 = Inventory()
    inv2 = Inventory()

    for eid, db_id, inv in [("player_1", 1, inv1), ("player_2", 2, inv2)]:
        entity = PlayerEntity(id=eid, name=f"hero_{db_id}", x=2, y=2, player_db_id=db_id)
        entity.stats = {"hp": 80, "max_hp": 100, "attack": 10, "xp": 0}
        game.player_entities[eid] = {
            "entity": entity, "room_key": "test_room",
            "inventory": inv, "db_id": db_id,
        }
        ws = AsyncMock()
        game.connection_manager.connect(eid, ws, "test_room")

    game.combat_manager._player_to_instance["player_1"] = "combat_1"
    game.combat_manager._player_to_instance["player_2"] = "combat_1"
    game.combat_manager._instances["combat_1"] = instance

    mock_player1 = AsyncMock()
    mock_player1.inventory = {}
    mock_player2 = AsyncMock()
    mock_player2.inventory = {}

    mock_item = MagicMock()
    mock_item.item_key = "healing_potion"
    mock_item.name = "Healing Potion"
    mock_item.category = "consumable"
    mock_item.stackable = True
    mock_item.charges = 3
    mock_item.effects = [{"type": "heal", "value": 25}]
    mock_item.usable_in_combat = True
    mock_item.usable_outside_combat = True
    mock_item.description = "Heals 25 HP"

    call_count = 0

    async def mock_get_by_id(session, db_id):
        nonlocal call_count
        call_count += 1
        if db_id == 1:
            return mock_player1
        return mock_player2

    with patch("server.net.handlers.combat.async_session") as mock_session, \
         patch("server.net.handlers.combat.player_repo") as mock_repo, \
         patch("server.net.handlers.combat.items_repo") as mock_items_repo:
        mock_sess = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_repo.get_by_id = AsyncMock(side_effect=mock_get_by_id)
        mock_repo.update_stats = AsyncMock()
        mock_items_repo.get_all = AsyncMock(return_value=[mock_item])

        game.kill_npc = AsyncMock()

        await _check_combat_end(instance, game)

    # Both players should have loot in runtime inventory
    assert inv1.has_item("healing_potion")
    assert inv1.get_quantity("healing_potion") == 1
    assert inv2.has_item("healing_potion")
    assert inv2.get_quantity("healing_potion") == 1


@pytest.mark.asyncio
async def test_combat_victory_disconnected_participant_skipped():
    """A participant not in player_entities is silently skipped for loot."""
    from server.net.handlers.combat import _check_combat_end
    from server.player.entity import PlayerEntity
    from server.items.inventory import Inventory

    game = _make_game()
    npc = _make_npc(loot_table="slime_loot")
    instance = _make_combat_instance()
    instance.participants = ["player_1", "player_2"]
    instance.participant_stats = {
        "player_1": {"hp": 80, "max_hp": 100, "attack": 10},
        "player_2": {"hp": 60, "max_hp": 100, "attack": 10},
    }

    room = MagicMock()
    room.get_npc.return_value = npc
    room.get_state.return_value = {"room_key": "test_room", "tiles": [], "entities": [], "objects": []}
    game.room_manager._rooms = {"test_room": room}
    game.room_manager.get_room = MagicMock(return_value=room)

    # Only player_1 is in player_entities — player_2 disconnected
    inv1 = Inventory()
    entity = PlayerEntity(id="player_1", name="hero", x=2, y=2, player_db_id=1)
    entity.stats = {"hp": 80, "max_hp": 100, "attack": 10, "xp": 0}
    game.player_entities["player_1"] = {
        "entity": entity, "room_key": "test_room",
        "inventory": inv1, "db_id": 1,
    }
    ws = AsyncMock()
    game.connection_manager.connect("player_1", ws, "test_room")

    game.combat_manager._player_to_instance["player_1"] = "combat_1"
    game.combat_manager._instances["combat_1"] = instance

    mock_player = AsyncMock()
    mock_player.inventory = {}

    mock_item = MagicMock()
    mock_item.item_key = "healing_potion"
    mock_item.name = "Healing Potion"
    mock_item.category = "consumable"
    mock_item.stackable = True
    mock_item.charges = 3
    mock_item.effects = [{"type": "heal", "value": 25}]
    mock_item.usable_in_combat = True
    mock_item.usable_outside_combat = True
    mock_item.description = "Heals 25 HP"

    with patch("server.net.handlers.combat.async_session") as mock_session, \
         patch("server.net.handlers.combat.player_repo") as mock_repo, \
         patch("server.net.handlers.combat.items_repo") as mock_items_repo:
        mock_sess = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_repo.get_by_id = AsyncMock(return_value=mock_player)
        mock_repo.update_stats = AsyncMock()
        mock_items_repo.get_all = AsyncMock(return_value=[mock_item])

        game.kill_npc = AsyncMock()

        # Should not raise — player_2 is silently skipped
        await _check_combat_end(instance, game)

    # player_1 got loot
    assert inv1.has_item("healing_potion")


@pytest.mark.asyncio
async def test_combat_defeat_no_loot():
    """Combat defeat does not generate loot."""
    from server.net.handlers.combat import _check_combat_end
    from server.player.entity import PlayerEntity
    from server.items.inventory import Inventory

    game = _make_game()
    instance = _make_combat_instance()
    instance.get_combat_end_result.return_value = {
        "victory": False,
        "rewards": {},
    }

    room = MagicMock()
    room.get_state.return_value = {"room_key": "test_room", "tiles": [], "entities": [], "objects": []}
    game.room_manager._rooms = {"test_room": room}
    game.room_manager.get_room = MagicMock(return_value=room)

    entity = PlayerEntity(id="player_1", name="hero", x=2, y=2, player_db_id=1)
    entity.stats = {"hp": 0, "max_hp": 100, "attack": 10, "xp": 0}
    inventory = Inventory()
    game.player_entities["player_1"] = {
        "entity": entity, "room_key": "test_room",
        "inventory": inventory, "db_id": 1,
    }

    ws = AsyncMock()
    game.connection_manager.connect("player_1", ws, "test_room")
    game.combat_manager._player_to_instance["player_1"] = "combat_1"
    game.combat_manager._instances["combat_1"] = instance

    with patch("server.net.handlers.combat.async_session") as mock_session, \
         patch("server.net.handlers.combat.player_repo") as mock_repo, \
         patch("server.net.handlers.combat.items_repo"):
        mock_sess = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_repo.update_stats = AsyncMock()

        game.respawn_player = AsyncMock()

        await _check_combat_end(instance, game)

    combat_end_msg = None
    for call in ws.send_json.call_args_list:
        msg = call.args[0]
        if msg.get("type") == "combat_end":
            combat_end_msg = msg
            break

    assert combat_end_msg is not None
    assert combat_end_msg["victory"] is False
    assert "loot" not in combat_end_msg
    assert not inventory.has_item("healing_potion")
