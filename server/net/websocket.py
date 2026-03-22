"""WebSocket endpoint for game communication."""
from __future__ import annotations

import json

from fastapi import WebSocket, WebSocketDisconnect

from server.net.connection_manager import ConnectionManager
from server.net.message_router import MessageRouter

# Module-level instances — wired by Game orchestrator in Story 1.8
router = MessageRouter()
connection_manager = ConnectionManager()


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
            await router.route(websocket, data)
    except WebSocketDisconnect:
        pass
