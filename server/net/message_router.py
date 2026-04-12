"""MessageRouter — routes incoming JSON messages by action field to handlers."""
from __future__ import annotations

from typing import Callable

from fastapi import WebSocket

from server.net.schemas import with_request_id


class MessageRouter:
    """Routes JSON messages to registered action handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable] = {}

    def register(self, action: str, handler: Callable) -> None:
        """Register a handler for a given action string."""
        self._handlers[action] = handler

    async def route(self, websocket: WebSocket, data: dict) -> None:
        """Look up handler by action and call it. Sends error if unknown."""
        action = data.get("action")
        handler = self._handlers.get(action)
        if handler is None:
            await websocket.send_json(
                with_request_id(
                    {"type": "error", "detail": f"Unknown action: {action}"},
                    data,
                )
            )
            return
        await handler(websocket, data)
