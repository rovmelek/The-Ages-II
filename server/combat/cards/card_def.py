"""Card definition dataclass — in-memory representation of a card."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from server.combat.cards.models import Card


@dataclass
class CardDef:
    """Immutable card definition used during combat."""

    card_key: str
    name: str
    cost: int
    effects: list[dict] = field(default_factory=list)
    description: str = ""

    @classmethod
    def from_db(cls, card: Card) -> CardDef:
        """Create a CardDef from a Card DB model instance."""
        return cls(
            card_key=card.card_key,
            name=card.name,
            cost=card.cost,
            effects=list(card.effects) if card.effects else [],
            description=card.description or "",
        )

    def to_dict(self) -> dict:
        """Serialize for client messages."""
        return {
            "card_key": self.card_key,
            "name": self.name,
            "cost": self.cost,
            "effects": self.effects,
            "description": self.description,
        }
