"""Item definition dataclass — in-memory representation of an item."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from server.items.models import Item


@dataclass
class ItemDef:
    """Immutable item definition."""

    item_key: str
    name: str
    category: str  # "consumable" or "material"
    stackable: bool = True
    charges: int = 1
    effects: list[dict] = field(default_factory=list)
    usable_in_combat: bool = False
    usable_outside_combat: bool = False
    description: str = ""
    tradeable: bool = True

    @classmethod
    def from_db(cls, item: Item) -> ItemDef:
        """Create an ItemDef from an Item DB model instance."""
        return cls(
            item_key=item.item_key,
            name=item.name,
            category=item.category,
            stackable=item.stackable,
            charges=item.charges,
            effects=list(item.effects) if item.effects else [],
            usable_in_combat=item.usable_in_combat,
            usable_outside_combat=item.usable_outside_combat,
            description=item.description or "",
            tradeable=item.tradeable if item.tradeable is not None else True,
        )

    def to_dict(self) -> dict:
        """Serialize for client messages."""
        return {
            "item_key": self.item_key,
            "name": self.name,
            "category": self.category,
            "stackable": self.stackable,
            "charges": self.charges,
            "effects": self.effects,
            "usable_in_combat": self.usable_in_combat,
            "usable_outside_combat": self.usable_outside_combat,
            "description": self.description,
            "tradeable": self.tradeable,
        }
