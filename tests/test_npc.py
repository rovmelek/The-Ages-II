"""Tests for NPC entity, templates, and hostile encounter detection."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from server.room.objects.npc import (
    NpcEntity,
    create_npc_from_template,
    load_npc_templates,
)
from server.room.room import RoomInstance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_room(width: int = 5, height: int = 5) -> RoomInstance:
    tile_data = [[0] * width for _ in range(height)]
    return RoomInstance(
        room_key="test",
        name="Test",
        width=width,
        height=height,
        tile_data=tile_data,
        spawn_points=[{"type": "player", "x": 0, "y": 0}],
    )


# ---------------------------------------------------------------------------
# NpcEntity creation from template
# ---------------------------------------------------------------------------

class TestNpcEntity:
    def test_create_npc_from_template(self):
        """NPC created from template has correct fields."""
        templates = [
            {
                "npc_key": "test_goblin",
                "name": "Test Goblin",
                "behavior_type": "hostile",
                "spawn_type": "persistent",
                "spawn_config": {"respawn_seconds": 60},
                "stats": {"hp": 50, "max_hp": 50, "attack": 10, "defense": 5},
                "loot_table": "goblin_loot",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "test.json"
            p.write_text(json.dumps(templates))
            npc_templates = load_npc_templates(Path(tmpdir))

        npc = create_npc_from_template("test_goblin", "npc_1", 3, 4, templates=npc_templates)
        assert npc is not None
        assert npc.npc_key == "test_goblin"
        assert npc.name == "Test Goblin"
        assert npc.x == 3
        assert npc.y == 4
        assert npc.behavior_type == "hostile"
        assert npc.stats["hp"] == 50
        assert npc.loot_table == "goblin_loot"
        assert npc.is_alive is True

    def test_create_npc_unknown_key_returns_none(self):
        npc = create_npc_from_template("nonexistent_key", "npc_x", 0, 0)
        assert npc is None

    def test_npc_to_dict(self):
        npc = NpcEntity(
            id="npc_1",
            npc_key="goblin",
            name="Goblin",
            x=2,
            y=3,
            behavior_type="hostile",
        )
        d = npc.to_dict()
        assert d["id"] == "npc_1"
        assert d["npc_key"] == "goblin"
        assert d["name"] == "Goblin"
        assert d["x"] == 2
        assert d["y"] == 3
        assert d["is_alive"] is True


# ---------------------------------------------------------------------------
# NPC template loading
# ---------------------------------------------------------------------------

class TestNpcTemplateLoading:
    def test_load_templates_from_json(self):
        templates = [
            {"npc_key": "bat", "name": "Bat", "behavior_type": "hostile", "stats": {"hp": 10}},
            {"npc_key": "rat", "name": "Rat", "behavior_type": "hostile", "stats": {"hp": 5}},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "mobs.json"
            p.write_text(json.dumps(templates))
            result = load_npc_templates(Path(tmpdir))

        assert "bat" in result
        assert "rat" in result
        assert result["bat"]["name"] == "Bat"

    def test_load_templates_nonexistent_dir(self):
        result = load_npc_templates(Path("/tmp/does_not_exist_xyz"))
        # Should not raise, returns existing templates dict
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Room NPC integration
# ---------------------------------------------------------------------------

class TestRoomNpcIntegration:
    def test_add_and_get_npc(self):
        room = _make_room()
        npc = NpcEntity(id="npc_1", npc_key="goblin", name="Goblin", x=3, y=3, behavior_type="hostile")
        room.add_npc(npc)
        assert room.get_npc("npc_1") is npc

    def test_remove_npc(self):
        room = _make_room()
        npc = NpcEntity(id="npc_1", npc_key="goblin", name="Goblin", x=3, y=3, behavior_type="hostile")
        room.add_npc(npc)
        removed = room.remove_npc("npc_1")
        assert removed is npc
        assert room.get_npc("npc_1") is None

    def test_npc_appears_in_room_state(self):
        """AC #4: NPC entities appear in room_state."""
        room = _make_room()
        npc = NpcEntity(id="npc_1", npc_key="goblin", name="Goblin", x=3, y=3, behavior_type="hostile")
        room.add_npc(npc)
        state = room.get_state()
        assert len(state["npcs"]) == 1
        assert state["npcs"][0]["id"] == "npc_1"
        assert state["npcs"][0]["name"] == "Goblin"


# ---------------------------------------------------------------------------
# Movement NPC encounter detection
# ---------------------------------------------------------------------------

class TestNpcEncounter:
    def test_hostile_alive_npc_triggers_encounter(self):
        """AC #2: Moving onto hostile alive NPC triggers mob_encounter."""
        room = _make_room()
        npc = NpcEntity(id="npc_1", npc_key="goblin", name="Goblin", x=1, y=0, behavior_type="hostile")
        room.add_npc(npc)

        from server.player.entity import PlayerEntity
        player = PlayerEntity(id="p1", name="Hero", x=0, y=0, player_db_id=1)
        room.add_entity(player)

        result = room.move_entity("p1", "right")
        assert result["success"] is True
        assert "mob_encounter" in result
        assert result["mob_encounter"]["entity_id"] == "npc_1"
        assert result["mob_encounter"]["name"] == "Goblin"

    def test_dead_npc_no_encounter(self):
        """AC #3: Dead NPC does not trigger encounter."""
        room = _make_room()
        npc = NpcEntity(id="npc_1", npc_key="goblin", name="Goblin", x=1, y=0, behavior_type="hostile", is_alive=False)
        room.add_npc(npc)

        from server.player.entity import PlayerEntity
        player = PlayerEntity(id="p1", name="Hero", x=0, y=0, player_db_id=1)
        room.add_entity(player)

        result = room.move_entity("p1", "right")
        assert result["success"] is True
        assert "mob_encounter" not in result

    def test_non_hostile_npc_no_encounter(self):
        """Non-hostile NPC (merchant) does not trigger encounter."""
        room = _make_room()
        npc = NpcEntity(id="npc_1", npc_key="merchant", name="Merchant", x=1, y=0, behavior_type="merchant")
        room.add_npc(npc)

        from server.player.entity import PlayerEntity
        player = PlayerEntity(id="p1", name="Hero", x=0, y=0, player_db_id=1)
        room.add_entity(player)

        result = room.move_entity("p1", "right")
        assert result["success"] is True
        assert "mob_encounter" not in result


# ---------------------------------------------------------------------------
# RoomManager NPC spawning
# ---------------------------------------------------------------------------

class TestRoomManagerNpcSpawn:
    def test_load_room_spawns_npcs(self):
        """AC #1: Room load creates NPCs from spawn points."""
        # Load templates first
        templates = [
            {"npc_key": "spawn_goblin", "name": "Spawn Goblin", "behavior_type": "hostile", "stats": {"hp": 30}},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "test.json"
            p.write_text(json.dumps(templates))
            npc_templates = load_npc_templates(Path(tmpdir))

        from server.room.manager import RoomManager

        # Create a fake RoomModel
        room_db = SimpleNamespace(
            room_key="spawn_test",
            name="Spawn Test",
            width=5,
            height=5,
            tile_data=[[0] * 5 for _ in range(5)],
            exits=[],
            objects=[],
            spawn_points=[
                {"type": "player", "x": 0, "y": 0},
                {"type": "npc", "npc_key": "spawn_goblin", "x": 3, "y": 3},
            ],
        )

        mgr = RoomManager()
        instance = mgr.load_room(room_db, npc_templates=npc_templates)
        npc = instance.get_npc("spawn_test_spawn_goblin_3_3")
        assert npc is not None
        assert npc.name == "Spawn Goblin"
        assert npc.x == 3
        assert npc.y == 3
