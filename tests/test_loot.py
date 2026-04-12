"""Tests for the shared loot system (Story 10.7)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pathlib import Path

from server.items.item_repo import load_loot_tables


from server.player.session import PlayerSession


def _ps(d: dict) -> PlayerSession:
    """Build a PlayerSession from a dict (test helper)."""
    entity = d["entity"]
    return PlayerSession(
        entity=entity,
        room_key=d["room_key"],
        db_id=d.get("db_id") or getattr(entity, "player_db_id", 0),
        inventory=d.get("inventory"),
        visited_rooms=set(d.get("visited_rooms", [])),
        pending_level_ups=d.get("pending_level_ups", 0),
    )


# ---------------------------------------------------------------------------
# Loot table data validation (data/loot/loot_tables.json)
# ---------------------------------------------------------------------------

_LOOT_TABLES = load_loot_tables(Path("data/loot"))


def test_loot_table_slime():
    items = _LOOT_TABLES["slime_loot"]
    assert len(items) == 1
    assert items[0]["item_key"] == "healing_potion"
    assert items[0]["quantity"] == 1


def test_loot_table_goblin():
    items = _LOOT_TABLES["goblin_loot"]
    assert len(items) == 1
    assert items[0]["item_key"] == "iron_shard"


def test_loot_table_bat():
    items = _LOOT_TABLES["bat_loot"]
    assert len(items) == 1
    assert items[0]["item_key"] == "antidote"


def test_loot_table_troll():
    items = _LOOT_TABLES["troll_loot"]
    assert len(items) == 2
    keys = {i["item_key"] for i in items}
    assert keys == {"healing_potion", "iron_shard"}


def test_loot_table_dragon():
    items = _LOOT_TABLES["dragon_loot"]
    assert len(items) == 2
    keys = {i["item_key"] for i in items}
    assert keys == {"fire_essence", "healing_potion"}
    for item in items:
        assert item["quantity"] == 2


def test_loot_table_common_chest():
    items = _LOOT_TABLES["common_chest"]
    assert len(items) == 2
    keys = {i["item_key"] for i in items}
    assert "healing_potion" in keys
    assert "iron_shard" in keys


def test_all_npc_loot_tables_present():
    """All NPC loot table keys referenced in base_npcs.json exist."""
    expected_keys = {"slime_loot", "goblin_loot", "bat_loot", "troll_loot", "dragon_loot"}
    for key in expected_keys:
        assert key in _LOOT_TABLES, f"Missing loot table: {key}"
        assert len(_LOOT_TABLES[key]) > 0, f"Empty loot table: {key}"


def test_loot_table_unknown_key():
    assert _LOOT_TABLES.get("nonexistent_table") is None


# ---------------------------------------------------------------------------
# Combat loot integration tests
# ---------------------------------------------------------------------------

def _mock_transaction():
    """Create a mock async context manager for game.transaction."""
    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_ctx)
    return mock_factory, mock_session


def _make_game():
    from server.app import Game
    game = Game()
    factory, _ = _mock_transaction()
    game.transaction = factory
    game.loot_tables = _LOOT_TABLES
    return game


def _make_npc(npc_id="npc_1", loot_table="slime_loot"):
    from server.room.npc import NpcEntity
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
    from server.combat.service import finalize_combat
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
    game.player_manager.set_session("player_1", _ps({
        "entity": entity, "room_key": "test_room",
        "inventory": inventory, "db_id": 1,
    }))

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

    with patch("server.combat.service.player_repo") as mock_repo, \
         patch("server.combat.service.items_repo") as mock_items_repo:
        mock_repo.get_by_id = AsyncMock(return_value=mock_player)
        mock_repo.update_stats = AsyncMock()
        mock_repo.update_inventory = AsyncMock()
        mock_items_repo.get_all = AsyncMock(return_value=[mock_item])

        game.kill_npc = AsyncMock()

        result = await finalize_combat(instance, game)

    # Check returned CombatEndResult for loot data
    assert result is not None
    assert result.end_result["victory"] is True
    assert "player_1" in result.player_loot
    assert len(result.player_loot["player_1"]) == 1
    assert result.player_loot["player_1"][0]["item_key"] == "healing_potion"
    assert result.player_loot["player_1"][0]["quantity"] == 1


@pytest.mark.asyncio
async def test_combat_victory_no_loot_table():
    """Combat victory with NPC that has empty loot_table produces no loot."""
    from server.combat.service import finalize_combat
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
    game.player_manager.set_session("player_1", _ps({
        "entity": entity, "room_key": "test_room",
        "inventory": inventory, "db_id": 1,
    }))

    ws = AsyncMock()
    game.connection_manager.connect("player_1", ws, "test_room")
    game.combat_manager._player_to_instance["player_1"] = "combat_1"
    game.combat_manager._instances["combat_1"] = instance

    with patch("server.combat.service.player_repo") as mock_repo, \
         patch("server.combat.service.items_repo"):
        mock_repo.update_stats = AsyncMock()

        game.kill_npc = AsyncMock()

        result = await finalize_combat(instance, game)

    # No loot for player_1 when NPC has no loot table
    assert result is not None
    assert "player_1" not in result.player_loot


@pytest.mark.asyncio
async def test_combat_victory_loot_updates_inventory():
    """Loot is added to player's runtime inventory on victory."""
    from server.combat.service import finalize_combat
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
    game.player_manager.set_session("player_1", _ps({
        "entity": entity, "room_key": "test_room",
        "inventory": inventory, "db_id": 1,
    }))

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

    with patch("server.combat.service.player_repo") as mock_repo, \
         patch("server.combat.service.items_repo") as mock_items_repo:
        mock_repo.get_by_id = AsyncMock(return_value=mock_player)
        mock_repo.update_stats = AsyncMock()
        mock_repo.update_inventory = AsyncMock()
        mock_items_repo.get_all = AsyncMock(return_value=[mock_item])

        game.kill_npc = AsyncMock()

        await finalize_combat(instance, game)

    # Runtime inventory should have the loot
    assert inventory.has_item("iron_shard")
    assert inventory.get_quantity("iron_shard") == 1

    # DB inventory should have been updated via repo
    inv_arg = mock_repo.update_inventory.call_args.args[2]
    assert inv_arg.get("iron_shard") == 1


@pytest.mark.asyncio
async def test_combat_victory_multi_player_same_loot():
    """Multiple players in combat each receive the same loot."""
    from server.combat.service import finalize_combat
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
        game.player_manager.set_session(eid, _ps({
            "entity": entity, "room_key": "test_room",
            "inventory": inv, "db_id": db_id,
        }))
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

    with patch("server.combat.service.player_repo") as mock_repo, \
         patch("server.combat.service.items_repo") as mock_items_repo:
        mock_repo.get_by_id = AsyncMock(side_effect=mock_get_by_id)
        mock_repo.update_stats = AsyncMock()
        mock_repo.update_inventory = AsyncMock()
        mock_items_repo.get_all = AsyncMock(return_value=[mock_item])

        game.kill_npc = AsyncMock()

        await finalize_combat(instance, game)

    # Both players should have loot in runtime inventory
    assert inv1.has_item("healing_potion")
    assert inv1.get_quantity("healing_potion") == 1
    assert inv2.has_item("healing_potion")
    assert inv2.get_quantity("healing_potion") == 1


@pytest.mark.asyncio
async def test_combat_victory_disconnected_participant_skipped():
    """A participant not in player_manager is silently skipped for loot."""
    from server.combat.service import finalize_combat
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

    # Only player_1 is in player_manager — player_2 disconnected
    inv1 = Inventory()
    entity = PlayerEntity(id="player_1", name="hero", x=2, y=2, player_db_id=1)
    entity.stats = {"hp": 80, "max_hp": 100, "attack": 10, "xp": 0}
    game.player_manager.set_session("player_1", _ps({
        "entity": entity, "room_key": "test_room",
        "inventory": inv1, "db_id": 1,
    }))
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

    with patch("server.combat.service.player_repo") as mock_repo, \
         patch("server.combat.service.items_repo") as mock_items_repo:
        mock_repo.get_by_id = AsyncMock(return_value=mock_player)
        mock_repo.update_stats = AsyncMock()
        mock_repo.update_inventory = AsyncMock()
        mock_items_repo.get_all = AsyncMock(return_value=[mock_item])

        game.kill_npc = AsyncMock()

        # Should not raise — player_2 is silently skipped
        await finalize_combat(instance, game)

    # player_1 got loot
    assert inv1.has_item("healing_potion")


@pytest.mark.asyncio
async def test_combat_defeat_no_loot():
    """Combat defeat does not generate loot."""
    from server.combat.service import finalize_combat
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
    game.player_manager.set_session("player_1", _ps({
        "entity": entity, "room_key": "test_room",
        "inventory": inventory, "db_id": 1,
    }))

    ws = AsyncMock()
    game.connection_manager.connect("player_1", ws, "test_room")
    game.combat_manager._player_to_instance["player_1"] = "combat_1"
    game.combat_manager._instances["combat_1"] = instance

    with patch("server.combat.service.player_repo") as mock_repo, \
         patch("server.combat.service.items_repo"):
        mock_repo.update_stats = AsyncMock()

        game.respawn_player = AsyncMock()

        result = await finalize_combat(instance, game)

    # Check returned CombatEndResult — defeat means no loot
    assert result is not None
    assert result.end_result["victory"] is False
    assert result.player_loot == {}
    assert not inventory.has_item("healing_potion")
