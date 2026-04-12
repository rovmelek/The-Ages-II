"""PlayerSession dataclass — typed session data managed by PlayerManager."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from server.items.inventory import Inventory
    from server.player.entity import PlayerEntity

@dataclass
class PlayerSession:
    """Typed session data for a connected player."""

    entity: PlayerEntity
    room_key: str
    db_id: int
    inventory: Inventory | None = None
    visited_rooms: set[str] = field(default_factory=set)
    pending_level_ups: int = 0
