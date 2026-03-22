"""WebSocket endpoint for game communication."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi import WebSocket, WebSocketDisconnect

if TYPE_CHECKING:
    from server.app import Game


def create_websocket_endpoint(game: Game):
    """Create a WebSocket endpoint function bound to the given Game instance."""

    async def websocket_endpoint(websocket: WebSocket) -> None:
        """Accept a WebSocket connection and route incoming messages."""
        await websocket.accept()
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_json(
                        {"type": "error", "detail": "Invalid JSON"}
                    )
                    continue
                if "action" not in data:
                    await websocket.send_json(
                        {"type": "error", "detail": "Missing action field"}
                    )
                    continue
                await game.router.route(websocket, data)
        except WebSocketDisconnect:
            await game.handle_disconnect(websocket)

    return websocket_endpoint
