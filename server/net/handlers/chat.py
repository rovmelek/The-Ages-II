"""Chat handler for WebSocket clients."""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import WebSocket

from server.core.config import settings
from server.net.auth_middleware import requires_auth
from server.player.session import PlayerSession

if TYPE_CHECKING:
    from server.app import Game


@requires_auth
async def handle_chat(
    websocket: WebSocket, data: dict, *, game: Game,
    entity_id: str, player_info: PlayerSession,
) -> None:
    """Handle the 'chat' action: room broadcast or whisper."""
    entity = player_info.entity
    room_key = player_info.room_key

    message = data.get("message", "").strip()
    if not message:
        return  # Ignore empty messages

    # Strip control characters (null bytes etc.) but keep \n and \r
    message = message.translate({i: None for i in range(32) if i not in (10, 13)})
    if not message:
        return

    if len(message) > settings.MAX_CHAT_MESSAGE_LENGTH:
        await websocket.send_json({
            "type": "error",
            "detail": f"Message too long (max {settings.MAX_CHAT_MESSAGE_LENGTH} characters)",
        })
        return

    whisper_to = data.get("whisper_to")

    if whisper_to:
        # Whisper to specific player
        target_ws = game.connection_manager.get_websocket(whisper_to)
        if target_ws is None:
            await websocket.send_json(
                {"type": "error", "detail": "Player not found"}
            )
            return

        msg = {
            "type": "chat",
            "sender": entity.name,
            "message": message,
            "whisper": True,
            "format": settings.CHAT_FORMAT,
        }
        await target_ws.send_json(msg)
        await websocket.send_json(msg)  # Copy to sender
    else:
        # Room broadcast
        msg = {
            "type": "chat",
            "sender": entity.name,
            "message": message,
            "whisper": False,
            "format": settings.CHAT_FORMAT,
        }
        await game.connection_manager.broadcast_to_room(room_key, msg)
