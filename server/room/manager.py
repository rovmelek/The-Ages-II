"""RoomManager — tracks active RoomInstance objects."""
from __future__ import annotations

from server.player.entity import PlayerEntity
from server.room.models import Room as RoomModel
from server.room.objects.npc import create_npc_from_template
from server.room.room import RoomInstance


class RoomManager:
    """Manages loaded room instances."""

    def __init__(self) -> None:
        self._rooms: dict[str, RoomInstance] = {}

    def get_room(self, room_key: str) -> RoomInstance | None:
        """Get a loaded room by key."""
        return self._rooms.get(room_key)

    def load_room(self, room_db: RoomModel) -> RoomInstance:
        """Create a RoomInstance from a DB Room model and track it."""
        instance = RoomInstance(
            room_key=room_db.room_key,
            name=room_db.name,
            width=room_db.width,
            height=room_db.height,
            tile_data=room_db.tile_data,
            exits=room_db.exits,
            objects=room_db.objects,
            spawn_points=room_db.spawn_points,
        )
        # Spawn NPCs from spawn points
        for sp in instance.spawn_points:
            if sp.get("type") == "npc":
                npc_key = sp.get("npc_key", "")
                npc_id = f"{room_db.room_key}_{npc_key}_{sp['x']}_{sp['y']}"
                npc = create_npc_from_template(npc_key, npc_id, sp["x"], sp["y"])
                if npc:
                    instance.add_npc(npc)

        self._rooms[room_db.room_key] = instance
        return instance

    def unload_room(self, room_key: str) -> None:
        """Remove a room from the active set."""
        self._rooms.pop(room_key, None)

    def transfer_entity(
        self,
        entity: PlayerEntity,
        from_room_key: str,
        to_room_key: str,
    ) -> RoomInstance | None:
        """Move an entity from one room to another. Returns target room or None."""
        source = self.get_room(from_room_key)
        if source:
            source.remove_entity(entity.id)

        target = self.get_room(to_room_key)
        if target is None:
            return None

        sx, sy = target.get_player_spawn()
        entity.x = sx
        entity.y = sy
        target.add_entity(entity)
        return target
