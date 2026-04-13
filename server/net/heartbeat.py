"""Heartbeat — periodic ping/pong for connection health monitoring."""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from server.core.config import settings

if TYPE_CHECKING:
    from server.app import Game


def start_heartbeat(game: Game, entity_id: str) -> None:
    """Start a heartbeat task for a connected player."""
    cancel_heartbeat(game, entity_id)  # Cancel any existing task first
    event = asyncio.Event()
    game._pong_events[entity_id] = event
    task = asyncio.create_task(_heartbeat_loop(game, entity_id))
    game._heartbeat_tasks[entity_id] = task


def cancel_heartbeat(game: Game, entity_id: str) -> None:
    """Cancel and remove heartbeat task and pong event for an entity."""
    task = game._heartbeat_tasks.pop(entity_id, None)
    if task and not task.done():
        task.cancel()
    game._pong_events.pop(entity_id, None)


async def _heartbeat_loop(game: Game, entity_id: str) -> None:
    """Send periodic pings and close connection if pong not received."""
    try:
        while True:
            await asyncio.sleep(settings.HEARTBEAT_INTERVAL_SECONDS)
            ws = game.connection_manager.get_websocket(entity_id)
            if ws is None:
                break
            try:
                await ws.send_json({"type": "ping"})
            except Exception:
                break
            event = game._pong_events.get(entity_id)
            if event is None:
                break
            event.clear()
            try:
                await asyncio.wait_for(
                    event.wait(),
                    timeout=settings.HEARTBEAT_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                # No pong received — close WebSocket
                try:
                    await ws.close(code=1001)
                except Exception:
                    pass
                break
    except asyncio.CancelledError:
        pass
