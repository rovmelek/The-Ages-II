"""RoomInstance — runtime room with tile grid, entities, and movement."""
from __future__ import annotations

from typing import TYPE_CHECKING

from server.player.entity import PlayerEntity
from server.room.tile import TileType, is_walkable

if TYPE_CHECKING:
    from server.room.objects.npc import NpcEntity

DIRECTION_DELTAS: dict[str, tuple[int, int]] = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}


class RoomInstance:
    """Live room holding a tile grid, entities, and movement validation."""

    def __init__(
        self,
        room_key: str,
        name: str,
        width: int,
        height: int,
        tile_data: list[list[int]],
        exits: list[dict] | None = None,
        objects: list[dict] | None = None,
        spawn_points: list[dict] | None = None,
    ):
        self.room_key = room_key
        self.name = name
        self.width = width
        self.height = height
        self._grid: list[list[int]] = tile_data
        self.exits: list[dict] = exits or []
        self.objects: list[dict] = objects or []
        self.spawn_points: list[dict] = spawn_points or []
        self._entities: dict[str, PlayerEntity] = {}
        self._npcs: dict[str, NpcEntity] = {}

        # Index interactive objects by id for quick lookup
        self._interactive_objects: dict[str, dict] = {}
        for obj in self.objects:
            if obj.get("id") and obj.get("category") == "interactive":
                self._interactive_objects[obj["id"]] = obj

        # Apply blocking static objects to the grid
        for obj in self.objects:
            if obj.get("category") == "static" and obj.get("blocking", False):
                ox, oy = obj["x"], obj["y"]
                if 0 <= oy < self.height and 0 <= ox < self.width:
                    self._grid[oy][ox] = TileType.WALL

    # --- Entity management ---

    def add_entity(self, entity: PlayerEntity) -> None:
        """Add an entity to the room."""
        self._entities[entity.id] = entity

    def remove_entity(self, entity_id: str) -> PlayerEntity | None:
        """Remove and return an entity, or None if not found."""
        return self._entities.pop(entity_id, None)

    def get_entities_at(self, x: int, y: int) -> list[PlayerEntity]:
        """Return all entities at the given tile."""
        return [e for e in self._entities.values() if e.x == x and e.y == y]

    def get_player_spawn(self) -> tuple[int, int]:
        """Return (x, y) of first player spawn point, fallback (0, 0)."""
        for sp in self.spawn_points:
            if sp.get("type") == "player":
                return (sp["x"], sp["y"])
        return (0, 0)

    def get_player_ids(self) -> list[str]:
        """Return all entity IDs currently in the room."""
        return list(self._entities.keys())

    def get_object(self, object_id: str) -> dict | None:
        """Return an interactive object dict by id, or None."""
        return self._interactive_objects.get(object_id)

    # --- NPC management ---

    def add_npc(self, npc: NpcEntity) -> None:
        """Add an NPC to the room."""
        self._npcs[npc.id] = npc

    def remove_npc(self, npc_id: str) -> NpcEntity | None:
        """Remove and return an NPC, or None if not found."""
        return self._npcs.pop(npc_id, None)

    def get_npc(self, npc_id: str) -> NpcEntity | None:
        """Get an NPC by id."""
        return self._npcs.get(npc_id)

    # --- Movement ---

    def move_entity(self, entity_id: str, direction: str) -> dict:
        """Move an entity in the given direction. Returns a result dict."""
        if direction not in DIRECTION_DELTAS:
            return {"success": False, "reason": "invalid_direction"}

        entity = self._entities.get(entity_id)
        if entity is None:
            return {"success": False, "reason": "entity_not_found"}

        dx, dy = DIRECTION_DELTAS[direction]
        nx, ny = entity.x + dx, entity.y + dy

        # Bounds check
        if not (0 <= nx < self.width and 0 <= ny < self.height):
            return {"success": False, "reason": "bounds"}

        # Walkability check (tile_data is row-major: [y][x])
        tile_value = self._grid[ny][nx]
        if not is_walkable(tile_value):
            return {"success": False, "reason": "wall"}

        # Move succeeds
        entity.x = nx
        entity.y = ny
        result: dict = {"success": True, "x": nx, "y": ny}

        # Exit detection
        if tile_value == TileType.EXIT:
            exit_info = next(
                (e for e in self.exits if e["x"] == nx and e["y"] == ny), None
            )
            if exit_info:
                result["exit"] = exit_info

        # NPC encounter detection
        for npc in self._npcs.values():
            if npc.x == nx and npc.y == ny and npc.is_alive and npc.behavior_type == "hostile":
                result["mob_encounter"] = {"entity_id": npc.id, "name": npc.name}
                break

        return result

    # --- Serialization ---

    def get_state(self) -> dict:
        """Return a serializable snapshot of the room."""
        entities = [
            {"id": e.id, "name": e.name, "x": e.x, "y": e.y}
            for e in self._entities.values()
        ]
        npcs = [npc.to_dict() for npc in self._npcs.values()]
        return {
            "room_key": self.room_key,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "tiles": self._grid,
            "entities": entities,
            "npcs": npcs,
            "exits": self.exits,
            "objects": self.objects,
        }
