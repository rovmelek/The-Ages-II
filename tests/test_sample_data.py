"""Tests for sample room and NPC data (Story 6-1) and cards/items data (Story 6-2)."""
import json
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.core.database import Base


# --- Fixtures ---


@pytest.fixture
async def db_session():
    """In-memory SQLite session with all tables created."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    import server.combat.cards.models  # noqa: F401
    import server.items.models  # noqa: F401
    import server.player.models  # noqa: F401
    import server.room.models  # noqa: F401
    import server.room.spawn_models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


DATA_DIR = Path("data")


# --- Story 6-1: Sample Room Data ---


class TestTownSquare:
    def test_file_exists(self):
        assert (DATA_DIR / "rooms" / "town_square.json").exists()

    def test_room_structure(self):
        with open(DATA_DIR / "rooms" / "town_square.json") as f:
            data = json.load(f)
        assert data["room_key"] == "town_square"
        assert data["name"] == "Town Square"
        assert data["width"] == 100
        assert data["height"] == 100

    def test_tile_data_dimensions(self):
        with open(DATA_DIR / "rooms" / "town_square.json") as f:
            data = json.load(f)
        assert len(data["tile_data"]) == 100
        assert all(len(row) == 100 for row in data["tile_data"])

    def test_has_spawn_points(self):
        with open(DATA_DIR / "rooms" / "town_square.json") as f:
            data = json.load(f)
        player_spawns = [sp for sp in data["spawn_points"] if sp["type"] == "player"]
        assert len(player_spawns) >= 1

    def test_has_static_objects(self):
        with open(DATA_DIR / "rooms" / "town_square.json") as f:
            data = json.load(f)
        static_objects = [o for o in data["objects"] if o["category"] == "static"]
        assert len(static_objects) >= 2  # trees, rocks, etc.

    def test_has_chests(self):
        with open(DATA_DIR / "rooms" / "town_square.json") as f:
            data = json.load(f)
        chests = [o for o in data["objects"] if o["type"] == "chest"]
        assert len(chests) >= 1
        for chest in chests:
            assert chest["state_scope"] == "player"

    def test_has_lever(self):
        with open(DATA_DIR / "rooms" / "town_square.json") as f:
            data = json.load(f)
        levers = [o for o in data["objects"] if o["type"] == "lever"]
        assert len(levers) >= 1
        assert levers[0]["state_scope"] == "room"

    def test_exit_to_dark_cave(self):
        with open(DATA_DIR / "rooms" / "town_square.json") as f:
            data = json.load(f)
        exits = data["exits"]
        cave_exits = [e for e in exits if e["target_room"] == "dark_cave"]
        assert len(cave_exits) >= 1

    def test_has_npc_spawns(self):
        """Town square has NPC spawns for gameplay."""
        with open(DATA_DIR / "rooms" / "town_square.json") as f:
            data = json.load(f)
        npc_spawns = [sp for sp in data["spawn_points"] if sp["type"] == "npc"]
        assert len(npc_spawns) > 0


class TestDarkCave:
    def test_file_exists(self):
        assert (DATA_DIR / "rooms" / "dark_cave.json").exists()

    def test_room_structure(self):
        with open(DATA_DIR / "rooms" / "dark_cave.json") as f:
            data = json.load(f)
        assert data["room_key"] == "dark_cave"
        assert data["name"] == "Dark Cave"
        assert data["width"] == 100
        assert data["height"] == 100

    def test_has_hostile_npc_spawns(self):
        with open(DATA_DIR / "rooms" / "dark_cave.json") as f:
            data = json.load(f)
        npc_spawns = [sp for sp in data["spawn_points"] if sp["type"] == "npc"]
        assert len(npc_spawns) >= 1
        npc_keys = {sp["npc_key"] for sp in npc_spawns}
        assert "slime" in npc_keys

    def test_has_chests(self):
        with open(DATA_DIR / "rooms" / "dark_cave.json") as f:
            data = json.load(f)
        chests = [o for o in data["objects"] if o["type"] == "chest"]
        assert len(chests) >= 1

    def test_exit_to_town_square(self):
        with open(DATA_DIR / "rooms" / "dark_cave.json") as f:
            data = json.load(f)
        exits = data["exits"]
        town_exits = [e for e in exits if e["target_room"] == "town_square"]
        assert len(town_exits) >= 1

    def test_has_static_objects(self):
        with open(DATA_DIR / "rooms" / "dark_cave.json") as f:
            data = json.load(f)
        static_objects = [o for o in data["objects"] if o["category"] == "static"]
        assert len(static_objects) >= 2  # rocks, stalagmites


class TestBaseNpcs:
    def test_file_exists(self):
        assert (DATA_DIR / "npcs" / "base_npcs.json").exists()

    def test_slime_definition(self):
        with open(DATA_DIR / "npcs" / "base_npcs.json") as f:
            npcs = json.load(f)
        slime = next((n for n in npcs if n["npc_key"] == "slime"), None)
        assert slime is not None
        assert slime["spawn_type"] == "persistent"
        assert slime["spawn_config"]["respawn_seconds"] == 60
        assert slime["hit_dice"] == 3
        assert slime["hp_multiplier"] == 10

    def test_cave_troll_definition(self):
        with open(DATA_DIR / "npcs" / "base_npcs.json") as f:
            npcs = json.load(f)
        troll = next((n for n in npcs if n["npc_key"] == "cave_troll"), None)
        assert troll is not None
        assert troll["spawn_type"] == "rare"
        assert troll["spawn_config"]["check_interval_hours"] == 12
        assert troll["spawn_config"]["spawn_chance"] == 0.15
        assert troll["hit_dice"] == 7
        assert troll["hp_multiplier"] == 28

    @pytest.mark.asyncio
    async def test_npc_templates_load(self):
        from server.room.npc import load_npc_templates
        templates = load_npc_templates(DATA_DIR / "npcs")
        assert "slime" in templates
        assert "cave_troll" in templates


# --- Story 6-2: Sample Cards & Items Data ---


class TestStarterCards:
    def test_file_exists(self):
        assert (DATA_DIR / "cards" / "starter_cards.json").exists()

    def test_has_15_cards(self):
        with open(DATA_DIR / "cards" / "starter_cards.json") as f:
            cards = json.load(f)
        assert len(cards) == 15

    def test_all_cards_have_required_fields(self):
        with open(DATA_DIR / "cards" / "starter_cards.json") as f:
            cards = json.load(f)
        for card in cards:
            assert "card_key" in card
            assert "name" in card
            assert "cost" in card
            assert "effects" in card
            assert isinstance(card["effects"], list)
            assert "description" in card

    def test_has_damage_cards(self):
        with open(DATA_DIR / "cards" / "starter_cards.json") as f:
            cards = json.load(f)
        damage_cards = [c for c in cards if any(e["type"] == "damage" for e in c["effects"])]
        assert len(damage_cards) >= 3

    def test_has_fire_and_physical_subtypes(self):
        with open(DATA_DIR / "cards" / "starter_cards.json") as f:
            cards = json.load(f)
        subtypes = set()
        for card in cards:
            for effect in card["effects"]:
                if effect["type"] == "damage" and "subtype" in effect:
                    subtypes.add(effect["subtype"])
        assert "fire" in subtypes
        assert "physical" in subtypes

    def test_has_heal_cards(self):
        with open(DATA_DIR / "cards" / "starter_cards.json") as f:
            cards = json.load(f)
        heal_cards = [c for c in cards if any(e["type"] == "heal" for e in c["effects"])]
        assert len(heal_cards) >= 1

    def test_has_shield_cards(self):
        with open(DATA_DIR / "cards" / "starter_cards.json") as f:
            cards = json.load(f)
        shield_cards = [c for c in cards if any(e["type"] == "shield" for e in c["effects"])]
        assert len(shield_cards) >= 1

    def test_has_dot_card(self):
        with open(DATA_DIR / "cards" / "starter_cards.json") as f:
            cards = json.load(f)
        dot_cards = [c for c in cards if any(e["type"] == "dot" for e in c["effects"])]
        assert len(dot_cards) >= 1

    def test_has_draw_card(self):
        with open(DATA_DIR / "cards" / "starter_cards.json") as f:
            cards = json.load(f)
        draw_cards = [c for c in cards if any(e["type"] == "draw" for e in c["effects"])]
        assert len(draw_cards) >= 1

    @pytest.mark.asyncio
    async def test_cards_load_into_db(self, db_session):
        from server.combat.cards import card_repo
        cards = await card_repo.load_cards_from_json(
            db_session, DATA_DIR / "cards" / "starter_cards.json"
        )
        assert len(cards) == 15


class TestBaseItems:
    def test_file_exists(self):
        assert (DATA_DIR / "items" / "base_items.json").exists()

    def test_has_required_items(self):
        with open(DATA_DIR / "items" / "base_items.json") as f:
            items = json.load(f)
        keys = {i["item_key"] for i in items}
        assert "healing_potion" in keys
        assert "antidote" in keys
        assert "fire_essence" in keys
        assert "iron_shard" in keys

    def test_healing_potion_config(self):
        with open(DATA_DIR / "items" / "base_items.json") as f:
            items = json.load(f)
        potion = next(i for i in items if i["item_key"] == "healing_potion")
        assert potion["charges"] == 3
        assert potion["usable_in_combat"] is True
        assert potion["usable_outside_combat"] is True
        assert any(e["type"] == "heal" and e["value"] == 25 for e in potion["effects"])

    def test_materials_not_usable(self):
        with open(DATA_DIR / "items" / "base_items.json") as f:
            items = json.load(f)
        materials = [i for i in items if i["category"] == "material"]
        assert len(materials) >= 2
        for mat in materials:
            assert mat["usable_in_combat"] is False
            assert mat["usable_outside_combat"] is False

    @pytest.mark.asyncio
    async def test_items_load_into_db(self, db_session):
        from server.items import item_repo
        items = await item_repo.load_items_from_json(
            db_session, DATA_DIR / "items" / "base_items.json"
        )
        assert len(items) == 4
