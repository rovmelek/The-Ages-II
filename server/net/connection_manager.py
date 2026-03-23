"""ConnectionManager — tracks WebSocket-to-player-entity-ID mappings."""
from __future__ import annotations

from fastapi import WebSocket


class ConnectionManager:
    """Maps player entity IDs to WebSocket connections."""

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._player_rooms: dict[str, str] = {}
        self._ws_to_entity: dict[int, str] = {}

    def connect(self, entity_id: str, websocket: WebSocket, room_key: str) -> None:
        """Register a player's WebSocket connection."""
        self._connections[entity_id] = websocket
        self._player_rooms[entity_id] = room_key
        self._ws_to_entity[id(websocket)] = entity_id

    def disconnect(self, entity_id: str) -> None:
        """Remove a player's connection."""
        ws = self._connections.pop(entity_id, None)
        self._player_rooms.pop(entity_id, None)
        if ws:
            self._ws_to_entity.pop(id(ws), None)

    def get_entity_id(self, websocket: WebSocket) -> str | None:
        """Reverse lookup: find entity_id for a WebSocket."""
        return self._ws_to_entity.get(id(websocket))

    def get_room(self, entity_id: str) -> str | None:
        """Get the room key for a player entity."""
        return self._player_rooms.get(entity_id)

    def get_websocket(self, entity_id: str) -> WebSocket | None:
        """Get the WebSocket for a player entity."""
        return self._connections.get(entity_id)

    def update_room(self, entity_id: str, room_key: str) -> None:
        """Update which room a player is in (for broadcast targeting)."""
        if entity_id in self._player_rooms:
            self._player_rooms[entity_id] = room_key

    async def send_to_player(self, entity_id: str, message: dict) -> None:
        """Send a JSON message to a specific player."""
        ws = self._connections.get(entity_id)
        if ws:
            await ws.send_json(message)

    async def broadcast_to_all(self, message: dict) -> None:
        """Send a JSON message to ALL connected players."""
        for ws in list(self._connections.values()):
            try:
                await ws.send_json(message)
            except Exception:
                pass  # Skip dead connections

    async def broadcast_to_room(
        self, room_key: str, message: dict, exclude: str | None = None
    ) -> None:
        """Send a JSON message to all players in a room."""
        for eid, rk in self._player_rooms.items():
            if rk == room_key and eid != exclude:
                ws = self._connections.get(eid)
                if ws:
                    await ws.send_json(message)
