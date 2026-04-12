"""Base classes for room objects."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from server.app import Game


@dataclass
class RoomObject:
    """Base for all objects placed in a room."""

    id: str
    type: str
    x: int
    y: int
    category: str  # "static", "interactive", "npc"
    state_scope: str | None = None  # "player" or "room"
    config: dict = field(default_factory=dict)
    room_key: str = ""


class InteractiveObject(RoomObject):
    """Base for objects a player can interact with."""

    async def interact(self, player_id: int, game: Game) -> dict[str, Any]:
        """Handle interaction. Returns result dict for interact_result message.

        Subclasses must override this method.
        """
        raise NotImplementedError
