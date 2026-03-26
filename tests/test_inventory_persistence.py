"""Tests for inventory persistence (Story 7.3)."""
from __future__ import annotations

import pytest

from server.items.inventory import Inventory
from server.items.item_def import ItemDef


# ---------------------------------------------------------------------------
# Inventory to_dict / from_dict round-trip tests
# ---------------------------------------------------------------------------

def _make_item(key: str, name: str = "Test Item") -> ItemDef:
    return ItemDef(item_key=key, name=name, category="consumable", charges=1)


def _make_lookup(*items: ItemDef):
    """Create a lookup callable from ItemDef list."""
    table = {i.item_key: i for i in items}
    return lambda k: table.get(k)


class TestInventoryRoundTrip:
    """Test to_dict() and from_dict() serialization."""

    def test_to_dict_empty(self):
        inv = Inventory()
        assert inv.to_dict() == {}

    def test_to_dict_with_items(self):
        inv = Inventory()
        potion = _make_item("healing_potion", "Healing Potion")
        shard = _make_item("iron_shard", "Iron Shard")
        inv.add_item(potion, 3)
        inv.add_item(shard, 1)

        d = inv.to_dict()
        assert d == {"healing_potion": 3, "iron_shard": 1}

    def test_from_dict_empty(self):
        inv = Inventory.from_dict({}, _make_lookup())
        assert inv.to_dict() == {}

    def test_from_dict_restores_items(self):
        potion = _make_item("healing_potion", "Healing Potion")
        shard = _make_item("iron_shard", "Iron Shard")
        lookup = _make_lookup(potion, shard)

        inv = Inventory.from_dict({"healing_potion": 3, "iron_shard": 1}, lookup)
        assert inv.get_quantity("healing_potion") == 3
        assert inv.get_quantity("iron_shard") == 1
        assert inv.get_item("healing_potion") is potion

    def test_round_trip(self):
        """from_dict(to_dict()) produces equivalent inventory."""
        potion = _make_item("healing_potion")
        shard = _make_item("iron_shard")

        original = Inventory()
        original.add_item(potion, 5)
        original.add_item(shard, 2)

        lookup = _make_lookup(potion, shard)
        restored = Inventory.from_dict(original.to_dict(), lookup)

        assert restored.to_dict() == original.to_dict()
        assert restored.get_quantity("healing_potion") == 5
        assert restored.get_quantity("iron_shard") == 2

    def test_from_dict_skips_unknown_items(self):
        """Items removed from game data are skipped gracefully."""
        potion = _make_item("healing_potion")
        lookup = _make_lookup(potion)  # iron_shard not in lookup

        inv = Inventory.from_dict(
            {"healing_potion": 1, "iron_shard": 2},
            lookup,
        )
        assert inv.has_item("healing_potion")
        assert not inv.has_item("iron_shard")
        assert inv.to_dict() == {"healing_potion": 1}

    def test_to_dict_after_use_charge(self):
        """to_dict() reflects consumed items."""
        potion = _make_item("healing_potion")
        inv = Inventory()
        inv.add_item(potion, 2)

        inv.use_charge("healing_potion")
        assert inv.to_dict() == {"healing_potion": 1}

        inv.use_charge("healing_potion")
        assert inv.to_dict() == {}
