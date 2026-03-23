"""Player inventory management — in-memory item tracking."""
from __future__ import annotations

from server.items.item_def import ItemDef


class Inventory:
    """Manages a player's items with unlimited stacking."""

    def __init__(self) -> None:
        # item_key -> {"item_def": ItemDef, "quantity": int}
        self._items: dict[str, dict] = {}

    def add_item(self, item_def: ItemDef, quantity: int = 1) -> None:
        """Add items to inventory. Stacks if already present."""
        if item_def.item_key in self._items:
            self._items[item_def.item_key]["quantity"] += quantity
        else:
            self._items[item_def.item_key] = {
                "item_def": item_def,
                "quantity": quantity,
            }

    def remove_item(self, item_key: str, quantity: int = 1) -> bool:
        """Remove quantity of an item. Returns False if not enough."""
        entry = self._items.get(item_key)
        if entry is None or entry["quantity"] < quantity:
            return False
        entry["quantity"] -= quantity
        if entry["quantity"] <= 0:
            del self._items[item_key]
        return True

    def get_item(self, item_key: str) -> ItemDef | None:
        """Get the ItemDef for an item in inventory."""
        entry = self._items.get(item_key)
        return entry["item_def"] if entry else None

    def get_quantity(self, item_key: str) -> int:
        """Get the quantity of an item in inventory."""
        entry = self._items.get(item_key)
        return entry["quantity"] if entry else 0

    def has_item(self, item_key: str) -> bool:
        """Check if item is in inventory."""
        return item_key in self._items

    def use_charge(self, item_key: str) -> bool:
        """Consume one charge of a consumable. Removes item if last charge.

        Returns False if item not in inventory.
        """
        entry = self._items.get(item_key)
        if entry is None:
            return False
        item_def = entry["item_def"]
        if item_def.charges > 0:
            # Charges-based item: decrement quantity when a "stack" is fully used
            # Each stack has `charges` uses. For simplicity, we track quantity of full items.
            # Using one charge = remove one from quantity.
            return self.remove_item(item_key, 1)
        return False

    def get_inventory(self) -> list[dict]:
        """Return serialized inventory for client."""
        result = []
        for item_key, entry in self._items.items():
            item_def = entry["item_def"]
            result.append({
                "item_key": item_key,
                "name": item_def.name,
                "category": item_def.category,
                "quantity": entry["quantity"],
                "charges": item_def.charges,
                "description": item_def.description,
            })
        return result
