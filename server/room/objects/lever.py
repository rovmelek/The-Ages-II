"""Lever interactive object — toggles tiles between wall and floor (room-shared state)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from server.room.objects.base import InteractiveObject
from server.room.objects.state import get_room_object_state, set_room_object_state
from server.room.tile import TileType

if TYPE_CHECKING:
    from server.app import Game


class LeverObject(InteractiveObject):
    """A lever that toggles a target tile between wall and floor for all players."""

    async def interact(self, player_id: int, game: Game) -> dict[str, Any]:
        room_key = self.room_key
        room = game.room_manager.get_room(room_key)
        if room is None:
            return {"status": "error", "message": "Room not found"}

        target_x = self.config.get("target_x", 0)
        target_y = self.config.get("target_y", 0)

        if not (0 <= target_x < room.width and 0 <= target_y < room.height):
            return {"status": "error", "message": "Invalid lever target coordinates"}

        async with game.transaction() as session:
            state = await get_room_object_state(session, room_key, self.id)
            active = state.get("active", False)

            # Toggle
            new_active = not active

            # Update the tile grid
            if new_active:
                new_tile = TileType.FLOOR
            else:
                new_tile = TileType.WALL
            room.set_tile(target_x, target_y, new_tile)

            # Persist state
            await set_room_object_state(session, room_key, self.id, {"active": new_active})

        # Broadcast tile change to all players in room
        await game.connection_manager.broadcast_to_room(
            room_key,
            {"type": "tile_changed", "x": target_x, "y": target_y, "tile_type": int(new_tile)},
        )

        return {"status": "toggled", "active": new_active, "target_x": target_x, "target_y": target_y}
