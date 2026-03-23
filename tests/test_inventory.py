"""Tests for player inventory management (Story 5-2)."""
import pytest

from server.items.inventory import Inventory
from server.items.item_def import ItemDef


# --- Helpers ---


def _potion(key="healing_potion", charges=3):
    return ItemDef(
        item_key=key,
        name="Healing Potion",
        category="consumable",
        charges=charges,
        effects=[{"type": "heal", "value": 25}],
        usable_in_combat=True,
        usable_outside_combat=True,
    )


def _material(key="iron_shard"):
    return ItemDef(
        item_key=key,
        name="Iron Shard",
        category="material",
        charges=0,
    )


# --- Tests ---


class TestInventory:
    def test_add_item(self):
        inv = Inventory()
        inv.add_item(_potion(), quantity=2)
        assert inv.has_item("healing_potion")
        assert inv.get_quantity("healing_potion") == 2

    def test_add_item_stacks(self):
        inv = Inventory()
        inv.add_item(_potion(), quantity=1)
        inv.add_item(_potion(), quantity=3)
        assert inv.get_quantity("healing_potion") == 4

    def test_remove_item(self):
        inv = Inventory()
        inv.add_item(_potion(), quantity=3)
        result = inv.remove_item("healing_potion", 2)
        assert result is True
        assert inv.get_quantity("healing_potion") == 1

    def test_remove_item_all(self):
        inv = Inventory()
        inv.add_item(_potion(), quantity=2)
        inv.remove_item("healing_potion", 2)
        assert inv.has_item("healing_potion") is False

    def test_remove_item_insufficient(self):
        inv = Inventory()
        inv.add_item(_potion(), quantity=1)
        result = inv.remove_item("healing_potion", 5)
        assert result is False
        assert inv.get_quantity("healing_potion") == 1

    def test_remove_item_not_found(self):
        inv = Inventory()
        result = inv.remove_item("nonexistent")
        assert result is False

    def test_get_item(self):
        inv = Inventory()
        potion = _potion()
        inv.add_item(potion)
        item_def = inv.get_item("healing_potion")
        assert item_def is not None
        assert item_def.item_key == "healing_potion"

    def test_get_item_not_found(self):
        inv = Inventory()
        assert inv.get_item("nonexistent") is None

    def test_has_item(self):
        inv = Inventory()
        assert inv.has_item("healing_potion") is False
        inv.add_item(_potion())
        assert inv.has_item("healing_potion") is True

    def test_use_charge_consumable(self):
        inv = Inventory()
        inv.add_item(_potion(charges=3), quantity=2)
        result = inv.use_charge("healing_potion")
        assert result is True
        assert inv.get_quantity("healing_potion") == 1

    def test_use_charge_last_removes_item(self):
        inv = Inventory()
        inv.add_item(_potion(charges=1), quantity=1)
        inv.use_charge("healing_potion")
        assert inv.has_item("healing_potion") is False

    def test_use_charge_material_no_charges(self):
        inv = Inventory()
        inv.add_item(_material(), quantity=5)
        result = inv.use_charge("iron_shard")
        assert result is False
        assert inv.get_quantity("iron_shard") == 5

    def test_use_charge_not_found(self):
        inv = Inventory()
        result = inv.use_charge("nonexistent")
        assert result is False

    def test_get_inventory_empty(self):
        inv = Inventory()
        assert inv.get_inventory() == []

    def test_get_inventory_serialized(self):
        inv = Inventory()
        inv.add_item(_potion(), quantity=2)
        inv.add_item(_material(), quantity=5)
        items = inv.get_inventory()
        assert len(items) == 2
        keys = {i["item_key"] for i in items}
        assert "healing_potion" in keys
        assert "iron_shard" in keys
        potion_entry = next(i for i in items if i["item_key"] == "healing_potion")
        assert potion_entry["quantity"] == 2
        assert potion_entry["name"] == "Healing Potion"
        assert "charges" in potion_entry
