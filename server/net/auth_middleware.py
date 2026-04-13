"""Authentication middleware decorator for WebSocket handlers."""
from __future__ import annotations

import functools
from typing import TYPE_CHECKING

from fastapi import WebSocket

from server.net.errors import ErrorCode, send_error
from server.player.session import PlayerSession

if TYPE_CHECKING:
    from server.app import Game


def requires_auth(fn):
    """Decorator that injects entity_id and player_info into handler functions.

    The outer (decorated) function retains the (websocket, data, *, game)
    signature so lambda registration in app.py is unaffected.  The inner
    function receives additional entity_id and player_info keyword arguments.
    """

    @functools.wraps(fn)
    async def wrapper(websocket: WebSocket, data: dict, *, game: Game) -> None:
        entity_id = game.connection_manager.get_entity_id(websocket)
        if entity_id is None:
            await send_error(websocket, ErrorCode.AUTH_REQUIRED, "Not logged in")
            return
        player_info = game.player_manager.get_session(entity_id)
        if player_info is None:
            await send_error(websocket, ErrorCode.AUTH_REQUIRED, "Not logged in")
            return
        await fn(websocket, data, game=game, entity_id=entity_id, player_info=player_info)

    return wrapper
