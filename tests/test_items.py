"""Tests for item definitions, loading, and repository (Story 5-1)."""
import json
import tempfile
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.core.database import Base
from server.items.item_def import ItemDef
from server.items.models import Item
from server.items import item_repo


# --- Fixtures ---


@pytest.fixture
async def db_session():
    """In-memory SQLite session with all tables created."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    import server.items.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


# --- ItemDef tests ---


class TestItemDef:
    def test_create_item_def(self):
        item = ItemDef(
            item_key="potion",
            name="Health Potion",
            category="consumable",
            charges=3,
            effects=[{"type": "heal", "value": 25}],
            usable_in_combat=True,
            usable_outside_combat=True,
        )
        assert item.item_key == "potion"
        assert item.name == "Health Potion"
        assert item.category == "consumable"
        assert item.charges == 3
        assert item.usable_in_combat is True
        assert item.usable_outside_combat is True

    def test_item_def_defaults(self):
        item = ItemDef(item_key="mat", name="Material", category="material")
        assert item.stackable is True
        assert item.charges == 1
        assert item.effects == []
        assert item.usable_in_combat is False
        assert item.usable_outside_combat is False
        assert item.description == ""

    def test_from_db(self):
        db_item = Item(
            id=1,
            item_key="test_item",
            name="Test",
            category="consumable",
            stackable=True,
            charges=2,
            effects=[{"type": "heal", "value": 10}],
            usable_in_combat=True,
            usable_outside_combat=False,
            description="A test item",
        )
        item_def = ItemDef.from_db(db_item)
        assert item_def.item_key == "test_item"
        assert item_def.name == "Test"
        assert item_def.charges == 2
        assert item_def.effects == [{"type": "heal", "value": 10}]
        assert item_def.usable_in_combat is True
        assert item_def.description == "A test item"

    def test_to_dict(self):
        item = ItemDef(
            item_key="sword",
            name="Sword",
            category="material",
            usable_in_combat=False,
        )
        d = item.to_dict()
        assert d["item_key"] == "sword"
        assert d["name"] == "Sword"
        assert d["category"] == "material"
        assert "usable_in_combat" in d
        assert "effects" in d


# --- Item repo tests ---


class TestItemRepo:
    @pytest.mark.asyncio
    async def test_load_items_from_json(self, db_session):
        items_data = [
            {
                "item_key": "potion",
                "name": "Potion",
                "category": "consumable",
                "charges": 1,
                "effects": [{"type": "heal", "value": 10}],
            }
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(items_data, f)
            f.flush()
            path = Path(f.name)

        loaded = await item_repo.load_items_from_json(db_session, path)
        assert len(loaded) == 1
        assert loaded[0].item_key == "potion"

    @pytest.mark.asyncio
    async def test_get_by_key(self, db_session):
        item = Item(
            item_key="test_key",
            name="Test",
            category="consumable",
        )
        db_session.add(item)
        await db_session.commit()

        found = await item_repo.get_by_key(db_session, "test_key")
        assert found is not None
        assert found.name == "Test"

    @pytest.mark.asyncio
    async def test_get_by_key_not_found(self, db_session):
        found = await item_repo.get_by_key(db_session, "nonexistent")
        assert found is None

    @pytest.mark.asyncio
    async def test_get_all(self, db_session):
        db_session.add(Item(item_key="a", name="A", category="consumable"))
        db_session.add(Item(item_key="b", name="B", category="material"))
        await db_session.commit()

        all_items = await item_repo.get_all(db_session)
        assert len(all_items) == 2

    @pytest.mark.asyncio
    async def test_upsert_existing_item(self, db_session):
        items_data = [
            {"item_key": "upsert", "name": "Original", "category": "consumable"}
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(items_data, f)
            f.flush()
            path = Path(f.name)

        await item_repo.load_items_from_json(db_session, path)

        # Update name
        items_data[0]["name"] = "Updated"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(items_data, f)
            f.flush()
            path2 = Path(f.name)

        loaded = await item_repo.load_items_from_json(db_session, path2)
        assert loaded[0].name == "Updated"

    @pytest.mark.asyncio
    async def test_load_base_items_json(self, db_session):
        """Verify the actual base_items.json file loads correctly."""
        base_path = Path("data/items/base_items.json")
        if not base_path.exists():
            pytest.skip("base_items.json not found")

        loaded = await item_repo.load_items_from_json(db_session, base_path)
        assert len(loaded) == 4
        keys = {item.item_key for item in loaded}
        assert "healing_potion" in keys
        assert "fire_essence" in keys
